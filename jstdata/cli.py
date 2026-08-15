import sys
import click
from typing import List, Union, Optional

from .client import ApiKeyNotSetError, JSTDataClient, InvalidApiKeyError
from .utils import common_params, common_search_params, format_and_print

client = JSTDataClient()

def resolve_id(value: str, search_func) -> str:
    """
    Helper to resolve a potential ID or search for it.
    Emphasizes 'Intent over IDs'.
    """
    # Simple heuristic: if it looks like an ID (no spaces, all lowercase/dashes),
    # we might still want to check if it's valid, but for now let's just use search
    # if it's not a perfect match.
    # In a real scenario, we might try a direct lookup first.
    try:
        results = search_func(value, limit=1)
        if results:
            return results[0].id
    except Exception:
        pass
    return value

@click.group()
def cli():
    """
    Jefferson Street CLI - A Research OS for Financial Data.
    """

@cli.command()
@click.option("--api-key", prompt="Enter your Jefferson Street API Key", hide_input=True, help="Your API Key")
def login(api_key):
    """
    Authenticate with the Jefferson Street API.
    """
    click.echo("Validating API key...")
    try:
        if client.validate_key(api_key):
            click.secho("Success! Authenticated.", fg="green")
            client._cfg.write(api_key=api_key)
            from .client import CONFIG_FILE
            click.echo(f"Configuration saved to {CONFIG_FILE.absolute()}")
        else:
            click.secho("Error: Invalid API key.", fg="red", err=True)
            sys.exit(1)
    except Exception as e:
        click.secho(f"Error during validation: {e}", fg="red", err=True)
        sys.exit(1)

@cli.group()
def config():
    """
    Manage CLI configuration.
    """
    pass

@config.command("show")
@click.option("--verbose", "-v", is_flag=True, help="Show advanced configuration like base URL")
def config_show(verbose):
    """
    Display current configuration.
    """
    if verbose:
        click.echo(f"Base URL: {client.base_url}")
    
    try:
        key = client.api_key
        masked_key = f"{key[:4]}...{key[-4:]}"
        click.echo(f"API Key: {masked_key}")
    except ApiKeyNotSetError:
        click.echo("API Key: Not set")

@config.command("set")
@click.argument("key", type=click.Choice(["api_key", "base_url"]))
@click.argument("value")
def config_set(key, value):
    """
    Update a configuration value. Valid keys are "api_key" and "base_url".
    """
    client._cfg.write(**{key: value})
    click.echo(f"Set {key} to {value}")

# --- Metric Commands ---

@cli.group()
def metric():
    """Commands for interacting with Metrics (themes)."""

@metric.command("ls")
@common_params
def list_metrics(limit, offset, format):
    """List all available metrics."""
    results = client.list_metrics(limit=limit, offset=offset)
    format_and_print(results, format)

@metric.command("show")
@click.argument("id")
@click.option("--format", default="pretty")
def show_metric(id, format):
    """Show details for a specific metric."""
    results = client.get_metric(id)
    format_and_print(results, format)

@metric.command("search")
@click.argument("query")
@common_search_params
def search_metrics(query, limit, offset, format):
    """Search for metrics by intent."""
    results = client.search_metrics(query, limit=limit, offset=offset)
    format_and_print(results, format)

@metric.command("series")
@click.argument("id")
@common_params
def metric_series(id, limit, offset, format):
    """List all series associated with a metric."""
    results = client.get_metric_series(id, limit=limit, offset=offset)
    format_and_print(results, format)

# --- Entity Commands ---

@cli.group()
def entity():
    """Commands for interacting with Entities (contexts)."""

@entity.command("show")
@click.argument("id")
@click.option("--format", default="pretty")
def show_entity(id, format):
    """Show details for a specific entity."""
    results = client.get_entity(id)
    format_and_print(results, format)

@entity.command("search")
@click.argument("query")
@common_search_params
def search_entities(query, limit, offset, format):
    """Search for entities by intent."""
    results = client.search_entities(query, limit=limit, offset=offset)
    format_and_print(results, format)

@entity.command("series")
@click.argument("id")
@common_params
def entity_series(id, limit, offset, format):
    """List all series associated with an entity."""
    results = client.get_entity_series(id, limit=limit, offset=offset)
    format_and_print(results, format)

@entity.command("relations")
@click.argument("id")
@common_params
def entity_relations(id, limit, offset, format):
    """Walk the entity graph."""
    results = client.get_entity_relations(id, limit=limit, offset=offset)
    format_and_print(results, format)

# --- Series Commands ---

@cli.group()
def series():
    """Commands for interacting with Series (data points)."""

@series.command("ls")
@common_params
def list_series(limit, offset, format):
    """List all available series."""
    results = client.list_series(limit=limit, offset=offset)
    format_and_print(results, format)

@series.command("show")
@click.argument("id")
@click.option("--format", default="pretty")
def show_series(id, format):
    """Show details for a specific series."""
    results = client.get_series(id)
    format_and_print(results, format)

@series.command("search")
@click.argument("query")
@common_search_params
def search_series(query, limit, offset, format):
    """Search for series by intent."""
    results = client.search_series(query, limit=limit, offset=offset)
    format_and_print(results, format)

# --- Query Command ---

@cli.command()
@click.option("--metric", multiple=True, help="Metric ID(s) or keywords")
@click.option("--entity", multiple=True, help="Entity ID(s) or keywords")
@click.option("--series", multiple=True, help="Series ID(s) or keywords")
@click.option("--frequency", type=click.Choice(["Annual", "Quarterly", "Monthly", "Daily", "Intraday"]))
@click.option("--start-date", help="Start date (YYYY-MM-DD)")
@click.option("--end-date", help="End date (YYYY-MM-DD)")
@click.option("--start-time", help="Start time (unix timestamp)")
@click.option("--end-time", help="End time (unix timestamp)")
@click.option("--fuzzy", is_flag=True, default=True, help="Try to resolve keywords to IDs automatically")
@common_params
def query(metric, entity, series, frequency, start_date, end_date, start_time, end_time, fuzzy, limit, offset, format):
    """
    The unified query engine. Mix and match metrics, entities, and series.
    """
    m_ids = list(metric)
    e_ids = list(entity)
    s_ids = list(series)

    if fuzzy:
        m_ids = [resolve_id(m, client.search_metrics) for m in m_ids]
        e_ids = [resolve_id(e, client.search_entities) for e in e_ids]
        s_ids = [resolve_id(s, client.search_series) for s in s_ids]

    results = client.query(
        metric=m_ids or None,
        entity=e_ids or None,
        series=s_ids or None,
        frequency=frequency,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        limit=limit,
        offset=offset
    )
    
    format_and_print(results, format)

@cli.command("steps")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable catalog")
def steps_cmd(as_json: bool) -> None:
    """List available investigation steps."""
    import json as json_lib

    from .workflows import list_steps

    specs = list_steps()
    if as_json:
        click.echo(json_lib.dumps([s.to_dict() for s in specs], indent=2))
        return
    if not specs:
        click.echo("No steps registered.")
        return
    for spec in specs:
        click.echo(f"{spec.id:20} {spec.name} — {spec.description}")


@cli.command("step")
@click.argument("step_id")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable step metadata")
def step_cmd(step_id: str, as_json: bool) -> None:
    """Describe a step: arguments, requirements, example."""
    import json as json_lib

    from .workflows import format_step_help, get_step

    try:
        spec = get_step(step_id)
    except KeyError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    if as_json:
        click.echo(json_lib.dumps(spec.to_dict(), indent=2))
        return
    click.echo(format_step_help(spec), nl=False)


@cli.command(
    "run",
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
@click.option(
    "--session",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Preload a session JSON into the pipeline",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=str),
    help="Default path for export session writes",
)
@click.pass_context
def run_cmd(ctx: click.Context, session: str | None, output: str | None) -> None:
    """Run one or more steps, daisy-chained with ':'

    \b
    jst run console
    jst run --session in.json console : console
    jst run company-selector --industry semiconductors : console
    """
    from .workflows import PipelineError, run_pipeline

    if not ctx.args:
        click.echo(ctx.get_help())
        raise SystemExit(2)
    try:
        run_pipeline(client, ctx.args, session_path=session, output_path=output)
    except KeyError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except PipelineError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

if __name__ == "__main__":
    try:
        cli()
    except ApiKeyNotSetError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        if sys.stdin.isatty():
            if click.confirm("Would you like to run 'jstdata login' now?"):
                # Use click.Context to invoke the login command
                ctx = cli.make_context("login", [])
                cli.invoke(ctx)
        else:
            sys.exit(1)
    except InvalidApiKeyError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)
