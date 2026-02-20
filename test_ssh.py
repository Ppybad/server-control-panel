import sys
import logging
import paramiko


def main():
    if len(sys.argv) < 5:
        print("Uso: python test_ssh.py <ip> <port> <user> <password>")
        sys.exit(1)

    ip = sys.argv[1]
    port = int(sys.argv[2])
    user = sys.argv[3]
    password = sys.argv[4]

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("paramiko").setLevel(logging.DEBUG)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip,
            port=port,
            username=user,
            password=password,
            timeout=10,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=20,
        )
        stdin, stdout, stderr = client.exec_command("uname -a || whoami")
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        print("STDOUT:")
        print(out)
        print("STDERR:")
        print(err)
    except Exception as e:
        print("ERROR:")
        print(repr(e))
    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

