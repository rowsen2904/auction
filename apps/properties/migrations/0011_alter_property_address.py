from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0010_property_developer_name_property_floor_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="property",
            name="address",
            field=models.CharField(db_index=True, max_length=255, verbose_name="Адрес"),
        ),
    ]
