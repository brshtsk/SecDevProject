pid_file = "/tmp/vault-agent.pid"

vault {
  address = "http://host.docker.internal:8200"
}

auto_auth {
  method "approle" {
    config = {
      role_id_file_path   = "/vault/role_id"
      secret_id_file_path = "/vault/secret_id"
    }
  }

  sink "file" {
    config = {
      path = "/vault/token"
    }
  }
}

template {
  source      = "/vault/templates/app.env.tmpl"
  destination = "/vault/rendered/app.env"
  perms       = "0644"
}

template {
  source      = "/vault/templates/db.env.tmpl"
  destination = "/vault/rendered/db.env"
  perms       = "0644"
}
