
import os
import random
import psycopg2

def read_env_vars(args):
    """Read environment variables and return as a dictionary."""
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "callback_db")
    db_user = os.getenv("DB_USER", "callback_user")
    db_pass = os.getenv("DB_PASS", "callback_pass")
    db_table = os.getenv("DB_TABLE", "callback_number")

    return {
        "db_host": db_host,
        "db_port": db_port,
        "db_name": db_name,
        "db_user": db_user,
        "db_pass": db_pass,
        "db_table": db_table,
    }


def db_connect(params):
    dbname = params.get("db_name")
    dbhost = params.get("db_host")
    dbport = params.get("db_port")
    dbuser = params.get("db_user")
    dbpass = params.get("db_pass")

    conn = psycopg2.connect(
        f"dbname={dbname} user={dbuser} password={dbpass} host={dbhost} port={dbport}"
    )
    return conn

def db_insert_callback_number(conn, table, src, dst, service_name):
    """Insert a new callback number into the database."""
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {table} (src, dst, service_id) "
            f"VALUES (%s, %s, "
            f"(SELECT id FROM callback_service WHERE name = %s))",
            (src, dst, service_name),
        )

def random_dst_number():
    # Generate a random number. Format: "0[5-9]XXXXXXX"
    prefix = "0" + str(random.randint(5, 9))
    number = prefix + "".join([str(random.randint(0, 9)) for _ in range(7)])
    return number

def randomize_dst(count: int) -> list:
    numbers = set()
    while len(numbers) < count:
        numbers.add(random_dst_number())
    return list(numbers)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Callback Number Inserter")
    parser.add_argument("--src", type=str, required=True, help="Source number")
    parser.add_argument("--dst", type=str, required=False, help="Destination number")
    parser.add_argument(
        "--service-name", type=str, required=True, help="Callback service name"
    )
    parser.add_argument("--count", type=int, default=1, help="Number of entries to insert")
    parser.add_argument("--randomize", action="store_true", help="Randomize destination numbers")
    args = parser.parse_args()

    env_vars = read_env_vars(args)
    conn = db_connect(env_vars)

    if args.randomize:
        dst_numbers = randomize_dst(args.count)
        for dst in dst_numbers:
            db_insert_callback_number(
                conn, "callback_number", args.src, dst, args.service_name
            )
        conn.commit()
        print(f"Inserted {args.count} randomized callback numbers successfully.")
        conn.close()
        return
    else:
        db_insert_callback_number(
            conn, "callback_number", args.src, args.dst, args.service_name
        )
        conn.commit()
        print("Callback number inserted successfully.")
        conn.close()

if __name__ == "__main__":
    main()