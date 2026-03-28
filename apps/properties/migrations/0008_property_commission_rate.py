import decimal
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0007_alter_property_property_class_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="commission_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Индивидуальная ставка комиссии застройщика для брокера (%).",
                max_digits=5,
                null=True,
                validators=[MinValueValidator(decimal.Decimal("0.00"))],
                verbose_name="Комиссия брокера (%)",
            ),
        ),
    ]
