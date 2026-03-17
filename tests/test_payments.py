import requests

BASE_URL = "http://127.0.0.1:8000"
# Replace with a real invoice ID from your database!
INVOICE_ID = 5 
HEADERS = {"Authorization": "Bearer YOUR_ADMIN_TOKEN_HERE"} # If you have auth enabled

def test_payment_flow():
    print("--- 1. Making a Partial Payment of $50 ---")
    payload_1 = {
        "amount": 50.00,
        "payment_method": "WIRE_TRANSFER",
        "reference_number": "TXN-998877"
    }
    res = requests.post(f"{BASE_URL}/billing/invoice/{INVOICE_ID}/pay", json=payload_1, headers=HEADERS)
    print(res.json())
    # You should check your database here: The invoice status should now be "PARTIAL"

    print("\n--- 2. Fetching Invoice to see the Balance Due ---")
    # Assuming you have a GET /billing/invoice/{id} endpoint (if not, check your DB)
    # The amount_paid should be 50.00, and balance_due will be calculated!

    print("\n--- 3. Paying the remaining balance (Let's assume the grand total was $93.00) ---")
    payload_2 = {
        "amount": 43.00, # 93.00 - 50.00
        "payment_method": "CREDIT_CARD",
        "reference_number": "STRIPE-123"
    }
    res2 = requests.post(f"{BASE_URL}/billing/invoice/{INVOICE_ID}/pay", json=payload_2, headers=HEADERS)
    print(res2.json())
    # Status should now automatically flip to "PAID"

    print("\n--- 4. Attempting to overpay (Should Fail) ---")
    payload_3 = {
        "amount": 10.00,
        "payment_method": "CASH"
    }
    res3 = requests.post(f"{BASE_URL}/billing/invoice/{INVOICE_ID}/pay", json=payload_3, headers=HEADERS)
    print(f"Expected Error: {res3.json()}") 
    # Should say "This invoice is already fully paid."

if __name__ == "__main__":
    test_payment_flow()