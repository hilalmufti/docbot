from openai import OpenAI

def main():
    client = OpenAI()
    completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Write a haiku about recursion in programming."
            }
        ]
    )
    print(completion.choices[0].message)
    print("hello world")

if __name__ == "__main__":
    main()