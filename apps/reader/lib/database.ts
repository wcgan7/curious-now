import postgres, { type Sql } from "postgres";

let client: Sql | null = null;

export function database(): Sql {
  if (client) {
    return client;
  }

  const databaseUrl =
    process.env.CURIOUS_NOW_V2_DATABASE_URL ?? process.env.DATABASE_URL;
  if (!databaseUrl) {
    throw new Error(
      "CURIOUS_NOW_V2_DATABASE_URL (or DATABASE_URL) must be configured",
    );
  }

  client = postgres(databaseUrl, {
    max: 3,
    idle_timeout: 20,
    connect_timeout: 10,
    prepare: false,
  });
  return client;
}
