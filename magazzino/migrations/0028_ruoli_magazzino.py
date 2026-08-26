from django.db import migrations


PERMISSION_CODENAME = "operare_magazzino"
OPERATOR_GROUP = "Operatori magazzino"
VIEWER_GROUP = "Consultazione"


def crea_ruoli(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="magazzino",
        model="movimento",
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=PERMISSION_CODENAME,
        defaults={
            "name": "Può eseguire operazioni e modifiche di magazzino",
        },
    )

    operatori, _ = Group.objects.get_or_create(name=OPERATOR_GROUP)
    operatori.permissions.add(permission)
    Group.objects.get_or_create(name=VIEWER_GROUP)


def elimina_ruoli(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=[OPERATOR_GROUP, VIEWER_GROUP]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0027_movimento_eseguito_da"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="movimento",
            options={
                "permissions": [
                    (
                        "operare_magazzino",
                        "Può eseguire operazioni e modifiche di magazzino",
                    ),
                ],
            },
        ),
        migrations.RunPython(crea_ruoli, elimina_ruoli),
    ]
