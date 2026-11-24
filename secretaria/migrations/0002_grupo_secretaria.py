from django.db import migrations


def criar(apps, schema_editor):
    apps.get_model("auth", "Group").objects.get_or_create(name="Secretaria")


class Migration(migrations.Migration):
    dependencies = [("secretaria", "0001_contas_email"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
