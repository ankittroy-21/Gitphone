import os
import sys
import uuid

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env vars before importing get_client
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from supabase_service import get_client  # noqa: E402


def test_rls():
    print("--- Testing RLS Isolation ---")

    user_a = "test_user_a_" + str(uuid.uuid4())[:8]
    user_b = "test_user_b_" + str(uuid.uuid4())[:8]

    if not os.environ.get("SUPABASE_JWT_SECRET"):
        print("WARNING: SUPABASE_JWT_SECRET is not set. The client will fall back to service_role, and this test will fail.")
        print("Please set SUPABASE_JWT_SECRET in your backend/.env file to run this test properly.")
        return

    # 1. Create a dummy user and staged file for User A using the global service_role client (bypasses RLS)
    service_client = get_client()

    print(f"Creating User A ({user_a}) and User B ({user_b}) via service_role...")
    service_client.table("users").insert([
        {"telegram_id": user_a, "github_token": "dummy", "default_repo": "dummy/repo"},
        {"telegram_id": user_b, "github_token": "dummy", "default_repo": "dummy/repo"}
    ]).execute()

    # Get User A's internal UUID
    user_a_record = service_client.table("users").select("id").eq("telegram_id", user_a).execute()
    user_a_id = user_a_record.data[0]["id"]

    print("Inserting a staged file for User A...")
    service_client.table("staged_files").insert({
        "user_id": user_a_id,
        "telegram_id": user_a,
        "filepath": "secret.txt",
        "diff": "+ secret data",
        "base_sha": "abcdef123"
    }).execute()

    # 2. Query using User B's JWT context
    print("Attempting to query User A's staged file using User B's JWT context...")
    client_b = get_client(user_b)

    # We explicitly ask for User A's data
    result = client_b.table("staged_files").select("*").eq("telegram_id", user_a).execute()

    if len(result.data) == 0:
        print("SUCCESS: RLS is working! User B was denied access to User A's data (0 rows returned).")
    else:
        print(f"FAIL: RLS failed! User B retrieved User A's data: {result.data}")

    # Cleanup
    print("Cleaning up test data...")
    service_client.table("users").delete().in_("telegram_id", [user_a, user_b]).execute()
    print("Done.")

if __name__ == "__main__":
    test_rls()
