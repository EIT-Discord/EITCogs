from schema import Schema, SchemaError


schema = Schema({
    'server': int,

    'roles': list,

    'channels': list,

    'semesters': {
        int: list
    }
})


def validate(config):
    """Makes sure the passed configuration file is valid"""
    try:
        return schema.validate(config)
    except SchemaError as e:
        print('EITBOT: The configuration file seems to be invalid:\n' + str(e))
