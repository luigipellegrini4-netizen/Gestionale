from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class AuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="operatore",
            password="password-di-test",
        )

    def test_login_page_is_public(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accedi al gestionale")

    def test_anonymous_user_is_redirected_to_login(self):
        target = reverse("situazione_magazzino")

        response = self.client.get(target)

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={target}",
        )

    def test_anonymous_post_cannot_change_stock(self):
        target = reverse("nuovo_carico")

        response = self.client.post(target, data={})

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={target}",
        )

    def test_authenticated_user_can_open_home(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)

    def test_authenticated_viewer_cannot_open_operational_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("nuovo_carico"))

        self.assertEqual(response.status_code, 403)

    def test_operator_can_open_operational_form(self):
        permission = Permission.objects.get(codename="operare_magazzino")
        self.user.user_permissions.add(permission)
        self.client.force_login(self.user)

        response = self.client.get(reverse("nuovo_carico"))

        self.assertEqual(response.status_code, 200)
