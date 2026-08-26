# Database migrations

Migration files are immutable and applied in lexical order. Never edit a migration that may
have been applied; add the next numbered migration instead. A fresh database applies every
file, while an existing database applies only files not yet recorded by the migration runner.
