from dotenv import load_dotenv

load_dotenv()

from gmail_client import get_message, list_messages_by_label
from graph import graph

LABEL = "0-Clients/client-cynthia"
MAX_EMAILS = 5

def main():
    stubs = list_messages_by_label(LABEL, max_results=MAX_EMAILS)
    print(f"Found {len(stubs)} emails labeled '{LABEL}\n")
    for stub in stubs:
        email = get_message(stub["id"])

        config = {"configurable": {"thread_id": email["message_id"]}}
        result = graph.invoke({"email_input": email}, config)

        print(f"From:           {email['from_addr']}")
        print(f"Subject:        {email['subject']}")
        print(f"Classification: {result['classification']}")
        print(f"Reasoning:      {result['reasoning']}")
        print("-" * 70)


if __name__ == "__main__":
    main()