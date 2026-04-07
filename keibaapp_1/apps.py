import os

from django.apps import AppConfig


class Keibaapp1Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keibaapp_1"

    def ready(self):
        create_flag = os.environ.get("CREATE_SUPERUSER", "False") == "True"
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not create_flag:
            return

        if not username or not email or not password:
            return

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            if not User.objects.filter(username=username).exists():
                User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password,
                )
                print("Superuser created successfully.")
            else:
                print("Superuser already exists.")
        except Exception as e:
            print(f"Superuser creation skipped: {e}")