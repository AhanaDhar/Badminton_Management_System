def register_management(app):
    from .people import bp as people
    from .scheduling import bp as scheduling
    from .records import bp as records
    from .finance import bp as finance
    from .analytics import bp as analytics

    for blueprint in (people, scheduling, records, finance, analytics):
        app.register_blueprint(blueprint)
