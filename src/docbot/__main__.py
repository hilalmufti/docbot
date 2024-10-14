from openai import OpenAI
from playwright.sync_api import sync_playwright, Page
import html2text
from bs4 import BeautifulSoup, NavigableString, Comment
from markdownify import markdownify as md
from sys import platform
from enum import Enum, auto
import re
import uuid
import time

EXCLUDED_TAGS = {
    "html",
    "head",
    "title",
    "meta",
    "iframe",
    "body",
    "script",
    "style",
    "path",
    "svg",
    "br",
    "::marker",
}

ATTRS = {"type", "placeholder", "aria-label", "title", "alt"}

SYSPROMPT = """
You are an agent controlling a browser. Your goal is to help the user find relevant documentation. You can save important information, such as useful text or links, to a scratchpad. The user's input will be provided in markdown format.

You are given:

    (1) an objective that you are trying to achieve
    (2) the URL of your current web page
    (3) a simplified text description of what's visible in the browser window (more on that below)

You can issue these commands:
    SCROLL UP - scroll up one page
    SCROLL DOWN - scroll down one page
    CLICK X - click on a given element. You can only click on links, buttons, and inputs!
    TYPESUBMIT X "TEXT" - same as TYPE above, except then it presses ENTER to submit the form
    SAVE TEXT "TEXT" - save specified text to the scratchpad for later reference
    SAVE LINK X "TEXT" - save the link with id X to the scratchpad for later reference

The format of the browser content is highly simplified; all formatting elements are stripped.
Interactive elements such as links, inputs, buttons are represented like this:

        <link id=1>text</link>
        <button id=2>text</button>
        <input id=3>text</input>

Images are rendered as their alt text like this:

        <img id=4 alt=""/>

Based on your given objective, issue whatever command you believe will get you closest to achieving your goal.
You always start on Google; you should submit a search query to Google that will take you to the best page for
achieving your objective. Then interact with that page to achieve your objective and save useful information.

If you find yourself on Google and there are no search results displayed yet, you should probably issue a command 
like "TYPESUBMIT 7 "search query"" to get to a more useful page.

Then, if you find yourself on a Google search results page, you might issue the command "CLICK 24" to click
on the first link in the search results. (If your previous command was a TYPESUBMIT your next command should
probably be a CLICK.)

Don't try to interact with elements that you can't see.

Here are some examples:

EXAMPLE 1:
==================================================
CURRENT BROWSER CONTENT:
------------------
<link id=0>About</link>
<link id=1>Store</link>
<link id=2 aria-label="Gmail ">Gmail</link>
<link id=3 aria-label="Search for Images ">Images</link>
<link id=4 aria-label="Google apps"/>
<link id=5 aria-label="Sign in">Sign in</link>
<img id=6 Google/>
<input id=7 Search Search/>
<button id=8 Search by voice/>
<button id=9 Search by image/>
<button id=10 Google Search/>
<button id=11 I'm Feeling Lucky/>
<link id=12>Advertising</link>
<link id=13>Business</link>
<link id=14>How Search works</link>
<link id=15>Our third decade of climate action: join us</link>
<link id=16>Privacy</link>
<link id=17>Terms</link>
<text id=18>Settings</text>
------------------
OBJECTIVE: Find the official Python documentation on list comprehensions
CURRENT URL: https://www.google.com/
YOUR COMMAND: 
TYPESUBMIT 7 "Python list comprehensions site:docs.python.org"
==================================================

EXAMPLE 2:
==================================================
CURRENT BROWSER CONTENT:
------------------
<link id=0>About</link>
<link id=1>Store</link>
<link id=2 aria-label="Gmail ">Gmail</link>
<link id=3 aria-label="Search for Images ">Images</link>
<link id=4 aria-label="Google apps"/>
<link id=5 aria-label="Sign in">Sign in</link>
<img id=6 Google/>
<input id=7 Search Search/>
<button id=8 Search by voice/>
<button id=9 Search by image/>
<button id=10 Google Search/>
<button id=11 I'm Feeling Lucky/>
<link id=12>Advertising</link>
<link id=13>Business</link>
<link id=14>How Search works</link>
<link id=15>Our third decade of climate action: join us</link>
<link id=16>Privacy</link>
<link id=17>Terms</link>
<text id=18>Settings</text>
------------------
OBJECTIVE: Find the documentation on Java's HashMap class
CURRENT URL: https://www.google.com/
YOUR COMMAND: 
TYPESUBMIT 7 "Java HashMap documentation site:docs.oracle.com"
==================================================

EXAMPLE 3:
==================================================
CURRENT BROWSER CONTENT:
------------------
<link id=0 alt="Amazon Web Services"/>
<input id=1 Search suggestions Search in AWS documentation text/>
<link id=2 aria-label="Contact Us">Contact Us</link>
<button id=3>English</button>
<link id=4>Create an AWS Account</link>
<link id=5>AWS</link>
<text id=6>Documentation</text>
<link id=7>Feedback</link>
<link id=8>Preferences</link>
<heading id=9/>
<text id=10>Welcome to AWS Documentation</text>
<text id=11>Find user guides, code samples, SDKs & toolkits, tutorials, API & CLI references, and more.</text>
<heading id=12/>
<text id=13>Featured content</text>
<img id=14 Amazon EC2 icon/>
<heading id=15/>
<link id=16>Amazon EC2</link>
<text id=17>Create and run virtual servers in the cloud</text>
<img id=18 Amazon S3 icon/>
<heading id=19/>
<link id=20>Amazon S3</link>
<text id=21>Object storage built to retrieve any amount of data from anywhere</text>
<img id=22 Amazon DynamoDB icon/>
<heading id=23/>
<link id=24>Amazon DynamoDB</link>
<text id=25>Managed NoSQL database service</text>
<img id=26 Amazon RDS icon/>
<heading id=27/>
<link id=28>Amazon RDS</link>
<text id=29>Set up, operate, and scale a relational database in the cloud</text>
<img id=30 AWS Lambda icon/>
<heading id=31/>
<link id=32>AWS Lambda</link>
<text id=33>Run code without thinking about servers</text>
<img id=34 Amazon VPC icon/>
<heading id=35/>
<link id=36>Amazon VPC</link>
<text id=37>Isolated cloud resources</text>
<img id=38 Decision guide icon/>
<heading id=39/>
<link id=40>Choosing a generative AI service</link>
<text id=41>Determine which AWS generative AI services are the best fit for your organization</text>
<img id=42 AWS container decision guide icon/>
<heading id=43/>
<link id=44>Choosing an AWS container service</link>
<text id=45>Evaluate AWS container services for your modern app development</text>
<img id=46 Decision guide icon/>
<heading id=47/>
<link id=48>Amazon Bedrock or Amazon SageMaker?</link>
<text id=49>Determine which service is the best fit for your needs</text>
<heading id=50/>
<text id=51>Getting started with AWS</text>
<text id=52>Learn the fundamentals and start building on AWS. Find best practices to help you launch your first application and get to know the AWS Management Console.</text>
<heading id=53/>
<link id=54 aria-label="Opens in a new tab">Set up your AWS environment</link>
<heading id=55/>
<link id=56 aria-label="Opens in a new tab">Getting Started Resource Center</link>
<heading id=57/>
<link id=58 aria-label="Opens in a new tab">AWS Cloud Security</link>
<img id=59/>
<heading id=60/>
<link id=61 aria-label="Opens in a new tab">Hands-on Tutorials</link>
<text id=62>Get started with step-by-step tutorials to launch your first application</text>
<img id=63/>
<heading id=64/>
<link id=65 aria-label="Opens in a new tab">AWS Prescriptive Guidance</link>
<text id=66>Resources to help you accelerate cloud adoption and modernization</text>
<img id=67/>
<heading id=68/>
<link id=69 aria-label="Opens in a new tab">AWS Architecture Center</link>
<text id=70>Learn how to architect more effectively on AWS</text>
<img id=71/>
<heading id=72/>
<link id=73 aria-label="Opens in a new tab">AWS Solutions Library</link>
<text id=74>Find vetted solutions and guidance for business and technical use cases</text>
<heading id=75/>
<text id=76>Product guides & references</text>
<text id=77>Find user guides, developer guides, API references, and CLI references for
                your AWS products.</text>
<button id=78 aria-label="Open help panel"/>
------------------
OBJECTIVE: "How do I create an AWS RDS database and connect to it from my EC2 instance?"
CURRENT URL: https://docs.aws.amazon.com/
YOUR COMMAND: 
TYPESUBMIT 1 "Connect RDS instance to EC2"
==================================================

The current browser content, objective, and current URL follow. Reply with your next command to the browser.

CURRENT BROWSER CONTENT:
------------------
$browser_content
------------------

OBJECTIVE: $objective
CURRENT URL: $url
PREVIOUS COMMAND: $previous_command
YOUR COMMAND:
"""

# html tags: [link, img, input, button, text, heading]

# also include current objective

# actions: click, type, typesubmit, fwd, bwd, save, read, navigate_to,


class Agent:
    def __init__(self):
        self.browser = (
            sync_playwright()
            .start()
            .chromium.launch(
                headless=False,
            )
        )

        self.page = self.browser.new_page()
        self.page.set_viewport_size({"width": 1280, "height": 1080})
        self.scratchpad_text = []
        self.scratchpad_links = []
        self.client = OpenAI()

    def go_to_page(self, url):
        self.page.goto(url=url if "://" in url else "http://" + url)
        self.cdp = self.page.context.new_cdp_session(self.page)
        self.page_element_buffer = {}

    def scroll(self, direction):
        if direction == "up":
            self.page.evaluate(
                "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop - window.innerHeight;"
            )
        elif direction == "down":
            self.page.evaluate(
                "(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop + window.innerHeight;"
            )

    def click(self, id):
        js = """
        links = document.getElementsByTagName("a");
        for (var i = 0; i < links.length; i++) {
            links[i].removeAttribute("target");
        }
        """
        self.page.evaluate(js)
        element = self.page_element_buffer.get(int(id))
        if element:
            x = element.get("center_x")
            y = element.get("center_y")
            self.page.mouse.click(x, y)
        else:
            print("Could not find element")


    def typesubmit(self, id, text):
        self.click(id)
        self.page.keyboard.type(text)
        self.page.keyboard.press("Enter")

    def remember_text(self, id, text):
        self.scratchpad_text.append(text)

    def remember_link(self, id, text):
        self.scratchpad_links.append(text)

    def parse_page(self):
        def convert_name(node_name, has_click_handler):
            if node_name == "a":
                return "link"
            if node_name == "input":
                return "input"
            if node_name == "img":
                return "img"
            if node_name == "textarea":
                return "input"  # Include textareas
            if (
                node_name.startswith("h") and node_name[1:].isdigit()
            ):  # Include headings
                return "heading"
            if node_name == "button" or has_click_handler:
                return "button"
            else:
                return "text"

        def find_attributes(attributes, keys):
            values = {}

            for [key_index, value_index] in zip(*(iter(attributes),) * 2):
                if value_index < 0:
                    continue
                key = strings[key_index]
                value = strings[value_index]

                if key in keys:
                    values[key] = value
                    keys.remove(key)

                    if not keys:
                        return values

            return values

        def add_to_hash_tree(hash_tree, tag, node_id, node_name, parent_id):
            parent_id_str = str(parent_id)
            if not parent_id_str in hash_tree:
                parent_name = strings[node_names[parent_id]].lower()
                grand_parent_id = parent[parent_id]

                add_to_hash_tree(
                    hash_tree, tag, parent_id, parent_name, grand_parent_id
                )

            is_parent_desc_anchor, anchor_id = hash_tree[parent_id_str]

            # even if the anchor is nested in another anchor, we set the "root" for all descendants to be ::Self
            if node_name == tag:
                value = (True, node_id)
            elif (
                is_parent_desc_anchor
            ):  # reuse the parent's anchor_id (which could be much higher in the tree)
                value = (True, anchor_id)
            else:
                value = (
                    False,
                    None,
                )  # not a descendant of an anchor, most likely it will become text, an interactive element or discarded

            hash_tree[str(node_id)] = value

            return value

        page = self.page
        page_element_buffer = self.page_element_buffer
        start = time.time()

        device_pixel_ratio = page.evaluate("window.devicePixelRatio")
        if platform == "darwin" and device_pixel_ratio == 1:  # lies
            device_pixel_ratio = 2

        win_upper_bound = page.evaluate("window.pageYOffset")
        win_left_bound = page.evaluate("window.pageXOffset")
        win_width = page.evaluate("window.screen.width")
        win_height = page.evaluate("window.screen.height")
        win_right_bound = win_left_bound + win_width
        win_lower_bound = win_upper_bound + win_height

        tree = self.cdp.send(
            "DOMSnapshot.captureSnapshot",
            {"computedStyles": [], "includeDOMRects": True, "includePaintOrder": True},
        )
        strings = tree["strings"]
        document = tree["documents"][0]
        nodes = document["nodes"]
        backend_node_id = nodes["backendNodeId"]
        attributes = nodes["attributes"]
        node_value = nodes["nodeValue"]
        parent = nodes["parentIndex"]
        node_types = nodes["nodeType"]
        node_names = nodes["nodeName"]
        is_clickable = set(nodes["isClickable"]["index"])

        text_value = nodes["textValue"]
        text_value_index = text_value["index"]
        text_value_values = text_value["value"]

        input_value = nodes["inputValue"]
        input_value_index = input_value["index"]
        input_value_values = input_value["value"]

        input_checked = nodes["inputChecked"]
        layout = document["layout"]
        layout_node_index = layout["nodeIndex"]
        bounds = layout["bounds"]

        cursor = 0
        html_elements_text = []

        child_nodes = {}
        elements_in_view_port = []

        anchor_ancestry = {"-1": (False, None)}
        button_ancestry = {"-1": (False, None)}
        # node_parent: 138, node_name: textarea, node_name_index: 252
        # node_parent: 38, node_name: textarea, node_name_index: 242
        for index, node_name_index in enumerate(node_names):
            node_parent = parent[index]
            node_name = strings[node_name_index].lower()

            is_ancestor_of_anchor, anchor_id = add_to_hash_tree(
                anchor_ancestry, "a", index, node_name, node_parent
            )

            is_ancestor_of_button, button_id = add_to_hash_tree(
                button_ancestry, "button", index, node_name, node_parent
            )

            try:
                cursor = layout_node_index.index(
                    index
                )  # todo replace this with proper cursoring, ignoring the fact this is O(n^2) for the moment
            except:
                continue

            if node_name in EXCLUDED_TAGS:
                continue

            [x, y, width, height] = bounds[cursor]
            x /= device_pixel_ratio
            y /= device_pixel_ratio
            width /= device_pixel_ratio
            height /= device_pixel_ratio

            elem_left_bound = x
            elem_top_bound = y
            elem_right_bound = x + width
            elem_lower_bound = y + height
            partially_is_in_viewport = (
                elem_left_bound < win_right_bound
                and elem_right_bound >= win_left_bound
                and elem_top_bound < win_lower_bound
                and elem_lower_bound >= win_upper_bound
            )

            if not partially_is_in_viewport:
                continue

            meta_data = []

            # inefficient to grab the same set of keys for kinds of objects but its fine for now
            element_attributes = find_attributes(
                attributes[index], ["type", "placeholder", "aria-label", "title", "alt"]
            )
            ancestor_exception = is_ancestor_of_anchor or is_ancestor_of_button
            ancestor_node_key = (
                None
                if not ancestor_exception
                else str(anchor_id)
                if is_ancestor_of_anchor
                else str(button_id)
            )
            ancestor_node = (
                None
                if not ancestor_exception
                else child_nodes.setdefault(str(ancestor_node_key), [])
            )

            if node_name == "#text" and ancestor_exception:
                text = strings[node_value[index]]
                if text == "|" or text == "•":
                    continue
                ancestor_node.append({"type": "type", "value": text})
            else:
                if (
                    node_name == "input" and element_attributes.get("type") == "submit"
                ) or node_name == "button":
                    node_name = "button"
                    element_attributes.pop(
                        "type", None
                    )  # prevent [button ... (button)..]

                for key in element_attributes:
                    if ancestor_exception:
                        ancestor_node.append(
                            {
                                "type": "attribute",
                                "key": key,
                                "value": element_attributes[key],
                            }
                        )
                    else:
                        meta_data.append(element_attributes[key])

            element_node_value = None

            if node_value[index] >= 0:
                element_node_value = strings[node_value[index]]
                if (
                    element_node_value == "|"
                ):  # commonly used as a seperator, does not add much context - lets save ourselves some token space
                    continue
            elif (
                node_name == "input"
                and index in input_value_index
                and element_node_value is None
            ):
                node_input_text_index = input_value_index.index(index)
                text_index = input_value_values[node_input_text_index]
                if node_input_text_index >= 0 and text_index >= 0:
                    element_node_value = strings[text_index]

            # remove redudant elements
            if ancestor_exception and (node_name != "a" and node_name != "button"):
                continue

            elements_in_view_port.append(
                {
                    "node_index": str(index),
                    "backend_node_id": backend_node_id[index],
                    "node_name": node_name,
                    "node_value": element_node_value,
                    "node_meta": meta_data,
                    "is_clickable": index in is_clickable,
                    "origin_x": int(x),
                    "origin_y": int(y),
                    "center_x": int(x + (width / 2)),
                    "center_y": int(y + (height / 2)),
                }
            )

        # NOTE: all we've done up to here is filter out elements that are not in the viewport
        # TODO: simplify the filtering

        # lets filter further to remove anything that does not hold any text nor has click handlers + merge text from leaf#text nodes with the parent
        elements_of_interest = []
        id_counter = 0
        for element in elements_in_view_port:
            node_index = element.get("node_index")
            node_name = element.get("node_name")
            node_value = element.get("node_value")
            is_clickable = element.get("is_clickable")
            origin_x = element.get("origin_x")
            origin_y = element.get("origin_y")
            center_x = element.get("center_x")
            center_y = element.get("center_y")
            meta_data = element.get("node_meta")

            inner_text = f"{node_value} " if node_value else ""
            meta = ""

            if node_index in child_nodes:
                for child in child_nodes.get(node_index):
                    entry_type = child.get("type")
                    entry_value = child.get("value")

                    if entry_type == "attribute":
                        entry_key = child.get("key")
                        meta_data.append(f'{entry_key}="{entry_value}"')
                    else:
                        inner_text += f"{entry_value} "

            if meta_data:
                meta_string = " ".join(meta_data)
                meta = f" {meta_string}"

            if inner_text != "":
                inner_text = f"{inner_text.strip()}"

            converted_node_name = convert_name(node_name, is_clickable)

            # not very elegant, more like a placeholder
            if (
                (converted_node_name != "button" or meta == "")
                and converted_node_name
                not in {"link", "input", "img", "textarea", "heading"}
                and inner_text.strip() == ""
            ):
                continue

            page_element_buffer[id_counter] = element

            if inner_text != "":
                elements_of_interest.append(
                    f"""<{converted_node_name} id={id_counter}{meta}>{inner_text}</{converted_node_name}>"""
                )
            else:
                elements_of_interest.append(
                    f"""<{converted_node_name} id={id_counter}{meta}/>"""
                )
            id_counter += 1
        print("Parsing time: {:0.2f} seconds".format(time.time() - start))
        return elements_of_interest
    
    def take_action(self, action):
        if action.startswith("SCROLL"):
            self.scroll(action.split()[1].lower())
        elif action.startswith("CLICK"):
            self.click(action.split()[1])
        elif action.startswith("TYPESUBMIT"):
            self.typesubmit(action.split()[1], " ".join(action.split()[2:]))
        elif action.startswith("SAVE TEXT"):
            self.remember_text(action.split()[1], action.split()[2])
        elif action.startswith("SAVE LINK"):
            self.remember_link(action.split()[1], action.split()[2])
        else:
            print("Invalid action")

    def prompt(self, objective, url, previous_command, browser_content):
        _prompt = SYSPROMPT
        _prompt = _prompt.replace("$objective", objective)
        _prompt = _prompt.replace("$url", url)
        _prompt = _prompt.replace("$previous_command", previous_command)
        _prompt = _prompt.replace("$browser_content", browser_content)
        messages = [
            {"role": "system", "content": "You are a helpful assistant that can control a browser to help the user find relevant documentation."},
            {"role": "user", "content": _prompt},
        ]
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        return response.choices[0].message.content


class TokenType(Enum):
    START_TAG = auto()
    END_TAG = auto()
    TEXT = auto()
    SELF_CLOSING_TAG = auto()


class Token:
    def __init__(self, type, tag_name=None, attributes=None, data=None):
        self.type = type
        self.tag_name = tag_name
        self.attributes = attributes or {}
        self.data = data


class Node:
    def __init__(self, tag_name=None, attributes=None, parent=None, data=None):
        self.tag_name = tag_name
        self.attributes = attributes or {}
        self.children = []
        self.parent = parent
        self.data = data  # For text nodes

    def __repr__(self):
        if self.tag_name:
            return f"Node(tag={self.tag_name}, children={len(self.children)})"
        else:
            return f"TextNode(data={self.data})"


def tokenize(html):
    tokens = []
    pos = 0
    length = len(html)
    tag_regex = re.compile(r"^<\/?([a-zA-Z][a-zA-Z0-9]*)\s*([^>]*)\/?>")
    attr_regex = re.compile(r'([a-zA-Z\-]+)(?:="([^"]*)")?')

    while pos < length:
        if html[pos] == "<":
            match = tag_regex.match(html[pos:])
            if match:
                full_tag = match.group(0)
                tag_name = match.group(1)
                attrs = match.group(2)
                is_end_tag = full_tag.startswith("</")
                is_self_closing = full_tag.endswith("/>") or tag_name.lower() in [
                    "br",
                    "img",
                    "hr",
                    "meta",
                    "input",
                    "link",
                ]

                attributes = dict(attr_regex.findall(attrs))

                if is_end_tag:
                    token = Token(TokenType.END_TAG, tag_name=tag_name)
                elif is_self_closing:
                    token = Token(
                        TokenType.SELF_CLOSING_TAG,
                        tag_name=tag_name,
                        attributes=attributes,
                    )
                else:
                    token = Token(
                        TokenType.START_TAG, tag_name=tag_name, attributes=attributes
                    )

                tokens.append(token)
                pos += len(full_tag)
            else:
                # Malformed tag, treat as text
                next_lt = html.find("<", pos + 1)
                data = html[pos : next_lt if next_lt != -1 else length]
                tokens.append(Token(TokenType.TEXT, data=data))
                pos = next_lt if next_lt != -1 else length
        else:
            next_lt = html.find("<", pos)
            data = html[pos : next_lt if next_lt != -1 else length]
            tokens.append(Token(TokenType.TEXT, data=data))
            pos = next_lt if next_lt != -1 else length

    return tokens


def tokenize_and_parse(html):
    tokens = tokenize(html)
    dom = parse(tokens)
    return dom


def parse(tokens):
    root = Node(tag_name="document")
    current = root
    stack = [root]

    for token in tokens:
        if token.type == TokenType.START_TAG:
            new_node = Node(
                tag_name=token.tag_name, attributes=token.attributes, parent=current
            )
            current.children.append(new_node)
            stack.append(new_node)
            current = new_node
        elif token.type == TokenType.END_TAG:
            if current.tag_name == token.tag_name:
                stack.pop()
                current = stack[-1] if stack else root
            else:
                # Mismatched tag, handle error or skip
                print(f"Warning: Mismatched tag {token.tag_name}")
        elif token.type == TokenType.SELF_CLOSING_TAG:
            new_node = Node(
                tag_name=token.tag_name, attributes=token.attributes, parent=current
            )
            current.children.append(new_node)
        elif token.type == TokenType.TEXT:
            text = token.data.strip()
            if text:
                text_node = Node(data=text, parent=current)
                current.children.append(text_node)

    return root


def print_dom(node, indent=0):
    spacer = "  " * indent
    if node.tag_name:
        attrs = " ".join([f'{k}="{v}"' for k, v in node.attributes.items()])
        print(f"{spacer}<{node.tag_name} {attrs}>")
        for child in node.children:
            print_dom(child, indent + 1)
        print(f"{spacer}</{node.tag_name}>")
    else:
        print(f"{spacer}{node.data}")


def main():
    client = OpenAI()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "click_link",
                # TODO
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_link",
                # TODO
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_note",
                # TODO
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_for",
                # TODO
            },
        },
    ]

    # Example Usage
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sample Page</title>
    </head>
    <body>
        <h1 class="title">Hello, World!</h1>
        <p>This is a <strong>sample</strong> paragraph.</p>
        <img src="image.jpg" alt="Sample Image" />
    </body>
    </html>
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Write a haiku about recursion in programming.",
            },
        ],
    )
    # response = completion.choices[0].message.content
    # print(completion.choices[0].message)
    print("hello world")
    cur = ""
    prev = ""
    try:
        agent = Agent()
        agent.go_to_page("https://docs.aws.amazon.com/")
        while True:
            objective = input()
            browser_content = "\n".join(agent.parse_page())
            prev = cur
            cur = agent.prompt(objective, agent.page.url, prev, browser_content)
            print("URL:", agent.page.url)
            print("Objective:", objective)
            print("\n-------------------------------- \n" + browser_content + "\n--------------------------------\n")
            print("Response:", cur)
            agent.take_action(cur)

    # print(agent.parse_page())
    except KeyboardInterrupt:
        agent.browser.close()


if __name__ == "__main__":
    main()
