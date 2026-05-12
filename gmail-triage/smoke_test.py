from gmail_client import list_messages_by_label, get_message

stubs = list_messages_by_label("0-Clients/client-cynthia", max_results=1)
print(f"Found {len(stubs)} messages")
for stub in stubs:
    email = get_message(stub["id"])
    # print(email)
    print(f"[{email['from_addr']}] {email['subject']}")