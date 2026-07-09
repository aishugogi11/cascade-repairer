from google.cloud import bigquery
from google.api_core.exceptions import Conflict, NotFound, BadRequest
import click
import yaml

_CLIENT = None


def get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = bigquery.Client()
    return _CLIENT


@click.group()
def cli():
    pass


@cli.command()
@click.argument("project_id")
@click.argument("dataset_id")
@click.option("--location", type=str, default=None,
              help="Dataset location (e.g. us-west1). BigQuery default if omitted.")
def create_dataset(project_id: str, dataset_id: str, location: str):
    client = get_client()
    dataset_ref = f"{project_id}.{dataset_id}"
    dataset = bigquery.Dataset(dataset_ref)
    if location:
        dataset.location = location
    try:
        client.create_dataset(dataset)
        print(f"Created dataset: {dataset_ref}")
    except Conflict:
        print(f"Dataset {dataset_ref} already exists")


@cli.command()
@click.argument("project_id")
@click.argument("dataset_id")
@click.argument("table_id")
@click.option("--field", "-f", "fields", type=(str, str), multiple=True,
              help="Define a schema field with NAME TYPE. Can be used multiple times.")
@click.option("--description", "-d", type=str, help="Table description.")
@click.option("--verbose", "-v", is_flag=True)
@click.option("--field-yaml-file", type=click.File("r"),
              help="YAML file defining the schema as a list of {field_name, field_type, [field_mode]} objects.")
@click.option("--dry-run", is_flag=True, help="If set, will not actually create the table.")
def create_table(project_id: str, dataset_id: str, table_id: str,
                 fields: tuple[tuple[str, str]], description: str,
                 verbose: bool, field_yaml_file, dry_run: bool):
    full_table_id = f"{project_id}.{dataset_id}.{table_id}"

    print(f"Creating table: {full_table_id}")
    print(f"Description: {description or 'No description provided'}")

    if fields and field_yaml_file:
        raise click.BadParameter("Cannot provide schema with both --field and --field-yaml-file.")
    if not fields and not field_yaml_file:
        raise click.UsageError("Must provide schema with either --field or --field-yaml-file.")

    schema_definition = []
    if field_yaml_file:
        if verbose:
            print(f"Loading schema from {field_yaml_file.name}")
        schema_from_file = yaml.safe_load(field_yaml_file)
        if not isinstance(schema_from_file, list):
            raise BadRequest("YAML file must contain a list of fields.")
        for item in schema_from_file:
            if not isinstance(item, dict) or "field_name" not in item or "field_type" not in item:
                raise BadRequest("Each item must be a dict with 'field_name' and 'field_type'.")
            # Optional 'field_mode' (e.g. REPEATED for ARRAY columns); defaults to NULLABLE.
            mode = item.get("field_mode", "NULLABLE")
            schema_definition.append((item["field_name"], item["field_type"], mode))
    else:
        # --field NAME TYPE pairs are always NULLABLE.
        schema_definition = [(name, ftype, "NULLABLE") for name, ftype in fields]

    schema = [bigquery.SchemaField(name, ftype, mode=mode) for name, ftype, mode in schema_definition]

    if verbose:
        print(f"{len(schema)} fields detected")
        for field in schema:
            print(f"- {field.name}: {field.field_type} ({field.mode})")

    table = bigquery.Table(full_table_id, schema=schema)
    table.description = description or ""

    if dry_run:
        print("[DRY RUN] Would create table now. Exiting.")
        return

    try:
        get_client().create_table(table)
        print(f"Table {full_table_id} created")
    except Conflict:
        print(f"Table {full_table_id} already exists -- no action taken")
    except NotFound:
        print(f"Dataset {dataset_id} not found in project {project_id}")


@cli.command()
@click.argument("project_id")
@click.argument("dataset_id")
@click.argument("table_id")
@click.option("--force", "-f", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
def truncate_table(project_id: str, dataset_id: str, table_id: str, force: bool, verbose: bool):
    full_table_id = f"{project_id}.{dataset_id}.{table_id}"
    print(f"Truncating table: {full_table_id}")
    if not force:
        click.echo("[Error] Will not truncate without forcing")
        return
    try:
        get_client().query_and_wait(f"TRUNCATE TABLE `{full_table_id}`")
        print(f"Truncated {full_table_id}")
    except NotFound:
        click.echo("[No Table Found - Exiting]")


@cli.command()
@click.argument("project_id")
@click.argument("dataset_id")
@click.argument("table_id")
@click.option("--force", "-f", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
def drop_table(project_id: str, dataset_id: str, table_id: str, force: bool, verbose: bool):
    full_table_id = f"{project_id}.{dataset_id}.{table_id}"
    if verbose:
        print(f"Dropping table: {full_table_id}")
    if not force:
        click.echo("[Error] Will not drop without forcing")
        return
    try:
        get_client().query_and_wait(f"DROP TABLE `{full_table_id}`")
        print(f"Dropped {full_table_id}")
    except NotFound:
        click.echo("[No Table Found - Exiting]")


if __name__ == "__main__":
    cli()
