# Generated for Property changes:
#   - re-add show_price_to_brokers (was added in 0012, removed in 0015)
#   - extend PropertyClasses with `elite`
#   - extend CommercialSubtypes with `warehouse` and `other`

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0015_remove_property_show_price_to_brokers"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="show_price_to_brokers",
            field=models.BooleanField(
                default=True, verbose_name="Показывать прайсовую цену брокерам"
            ),
        ),
        migrations.AlterField(
            model_name="property",
            name="property_class",
            field=models.CharField(
                blank=True,
                choices=[
                    ("economy", "Economy"),
                    ("comfort", "Comfort"),
                    ("business", "Business"),
                    ("premium", "Premium"),
                    ("elite", "Elite"),
                ],
                db_index=True,
                max_length=32,
                null=True,
                verbose_name="Класс объекта",
            ),
        ),
        migrations.AlterField(
            model_name="property",
            name="commercial_subtype",
            field=models.CharField(
                blank=True,
                choices=[
                    ("retail", "Retail"),
                    ("office", "Office"),
                    ("warehouse", "Warehouse"),
                    ("other", "Other"),
                ],
                db_index=True,
                max_length=32,
                null=True,
                verbose_name="Подтип коммерции",
            ),
        ),
    ]
