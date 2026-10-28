import re


def formatar_cpf(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None

    digitos = re.sub(r"\D", "", texto)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        raise ValueError("O CPF deve conter 11 dígitos válidos.")

    for tamanho in (9, 10):
        soma = sum(int(digitos[indice]) * (tamanho + 1 - indice) for indice in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(digitos[tamanho]):
            raise ValueError("O CPF deve conter 11 dígitos válidos.")

    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
