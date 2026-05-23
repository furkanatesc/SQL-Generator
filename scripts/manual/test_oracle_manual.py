import oracledb
import sqlite3

try:
    conn_sq = sqlite3.connect("sqlgen.db")
    conn_sq.row_factory = sqlite3.Row
    c = conn_sq.cursor()
    c.execute("SELECT key, value FROM configs")
    configs = {row["key"]: row["value"] for row in c.fetchall()}
    
    pwd = configs.get("target_oracle_password", "")
    user = configs.get("target_oracle_user", "santysm")
    service = configs.get("target_oracle_service", "hastane")
    host = configs.get("target_oracle_host", "192.168.56.226")
    port = int(configs.get("target_oracle_port", "1521"))
    
    print(f"Connecting to {user} / {service} at {host}:{port}...")
    
    try:
        dsn = oracledb.makedsn(host, port, service_name=service)
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
        print("Connection successful with SERVICE_NAME!")
    except Exception as e1:
        print(f"Service name failed: {e1}")
        print("Trying with SID instead...")
        dsn = oracledb.makedsn(host, port, sid=service)
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
        print("Connection successful with SID!")
    
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM all_tables WHERE owner = :owner", {"owner": user.upper()})
    count = cursor.fetchone()[0]
    print(f"Tables owned by {user.upper()}: {count}")
    
    if count == 0:
        cursor.execute("SELECT owner, count(*) FROM all_tables GROUP BY owner ORDER BY count(*) DESC FETCH FIRST 5 ROWS ONLY")
        print("Top table owners in DB:")
        for row in cursor.fetchall():
            print(f" - {row[0]}: {row[1]} tables")
            
except Exception as e:
    print("Fatal Error:", e)
