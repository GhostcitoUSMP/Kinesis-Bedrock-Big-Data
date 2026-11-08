import unittest

from producer.producer import postal_code, transaction_event


class ProducerTests(unittest.TestCase):
    def test_normalizes_csv_row(self):
        row = {
            "id": "1", "date": "2010-01-01 00:01:00", "client_id": "2", "card_id": "3",
            "amount": "$-77.00", "use_chip": " Swipe Transaction ", "merchant_id": "4",
            "merchant_city": "", "merchant_state": "ND", "zip": "58523.0", "mcc": "5", "errors": "",
        }
        event = transaction_event(row, 2)
        self.assertEqual(event["amount"], -77.0)
        self.assertEqual(event["zip"], "58523")
        self.assertIsNone(event["errors"])
        self.assertIsNone(event["merchant_city"])

    def test_postal_code_preserves_five_digit_format(self):
        self.assertEqual(postal_code("01234"), "01234")
        self.assertEqual(postal_code("58523.0"), "58523")


if __name__ == "__main__":
    unittest.main()
