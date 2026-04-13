from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0011_property_project_comment"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="commercial_subtype",
            field=models.CharField(
                blank=True,
                choices=[("retail", "Retail"), ("office", "Office")],
                db_index=True,
                max_length=32,
                null=True,
                verbose_name="Подтип коммерции",
            ),
        ),
    ]
