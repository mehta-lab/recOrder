import click
import yaml


def echo_settings(settings):
    click.echo(yaml.dump(settings.dict()))


def echo_headline(headline):
    click.echo(click.style(headline, fg="green"))
