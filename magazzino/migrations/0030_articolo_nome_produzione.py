from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0029_vincoli_articoli_ricette"),
    ]

    operations = [
        migrations.AddField(
            model_name="articolo",
            name="nome_produzione",
            field=models.CharField(
                blank=True,
                help_text="Nome semplice mostrato nelle ricette e nelle produzioni.",
                max_length=200,
            ),
        ),
    ]
