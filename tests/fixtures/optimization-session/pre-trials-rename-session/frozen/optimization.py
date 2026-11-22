import json
def validate_arguments(args):
    assert not args
    return {}
def arguments(candidate, output, settings):
    return [str(candidate), str(output)]
def assess(directory, settings, execution):
    return json.loads((directory / 'measurement/result.json').read_text())
