from math import atan2, cos, radians, sin, sqrt


def garantir_tabela_marco_zero(conexao):
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes_sistema (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            marco_zero_latitude DOUBLE PRECISION,
            marco_zero_longitude DOUBLE PRECISION,
            marco_zero_endereco TEXT NOT NULL DEFAULT '',
            raio_ponto_metros SMALLINT NOT NULL DEFAULT 100
                CHECK (raio_ponto_metros BETWEEN 1 AND 100),
            qr_ponto_token TEXT,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conexao.execute(
        "ALTER TABLE configuracoes_sistema ADD COLUMN IF NOT EXISTS qr_ponto_token TEXT"
    )
    conexao.execute(
        "INSERT INTO configuracoes_sistema (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    )


def obter_marco_zero(conexao):
    garantir_tabela_marco_zero(conexao)
    return conexao.execute(
        """
        SELECT marco_zero_latitude, marco_zero_longitude,
               marco_zero_endereco, raio_ponto_metros
        FROM configuracoes_sistema WHERE id = 1
        """
    ).fetchone()


def calcular_distancia_metros(latitude_a, longitude_a, latitude_b, longitude_b):
    """Calcula a distância entre duas coordenadas usando a fórmula de Haversine."""
    raio_terra_metros = 6_371_000
    diferenca_latitude = radians(latitude_b - latitude_a)
    diferenca_longitude = radians(longitude_b - longitude_a)
    termo = (
        sin(diferenca_latitude / 2) ** 2
        + cos(radians(latitude_a))
        * cos(radians(latitude_b))
        * sin(diferenca_longitude / 2) ** 2
    )
    return 2 * raio_terra_metros * atan2(sqrt(termo), sqrt(1 - termo))
