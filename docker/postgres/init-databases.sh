#!/usr/bin/env bash
set -eu

: "${APP_DATABASE_NAME:?APP_DATABASE_NAME is required}"
: "${APP_DATABASE_USER:?APP_DATABASE_USER is required}"
: "${APP_DATABASE_PASSWORD:?APP_DATABASE_PASSWORD is required}"
: "${KESTRA_DATABASE_NAME:?KESTRA_DATABASE_NAME is required}"
: "${KESTRA_DATABASE_USER:?KESTRA_DATABASE_USER is required}"
: "${KESTRA_DATABASE_PASSWORD:?KESTRA_DATABASE_PASSWORD is required}"

# Create isolated login roles and databases without interpolating credentials into SQL.
psql --set=ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres \
  --set=app_database="${APP_DATABASE_NAME}" \
  --set=app_user="${APP_DATABASE_USER}" \
  --set=app_password="${APP_DATABASE_PASSWORD}" \
  --set=kestra_database="${KESTRA_DATABASE_NAME}" \
  --set=kestra_user="${KESTRA_DATABASE_USER}" \
  --set=kestra_password="${KESTRA_DATABASE_PASSWORD}" <<'SQL'
select format('create role %I login password %L', :'app_user', :'app_password')
 where not exists (select 1 from pg_roles where rolname = :'app_user') \gexec

select format('create role %I login password %L', :'kestra_user', :'kestra_password')
 where not exists (select 1 from pg_roles where rolname = :'kestra_user') \gexec

select format('create database %I owner %I', :'app_database', :'app_user')
 where not exists (select 1 from pg_database where datname = :'app_database') \gexec

select format('create database %I owner %I', :'kestra_database', :'kestra_user')
 where not exists (select 1 from pg_database where datname = :'kestra_database') \gexec
SQL

# Install the application extensions into the application-owned database.
psql --set=ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${APP_DATABASE_NAME}" <<'SQL'
create extension if not exists vector;
create extension if not exists pg_textsearch;
SQL
