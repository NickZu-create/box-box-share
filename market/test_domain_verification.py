from django.test import Client, TestCase


class DomainVerification(TestCase):
    def test_wechat_file_is_served_exactly_at_the_root(self):
        response=Client().get('/bbc52af11e58bbe2adf42249ed6e004b.txt')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'9c999473e7f72d4ece9fd0ae47ef0f55874a39c3')
        self.assertTrue(response['Content-Type'].startswith('text/plain'))

    def test_other_text_files_are_not_found(self):
        self.assertEqual(Client().get('/anything-else.txt').status_code,404)
