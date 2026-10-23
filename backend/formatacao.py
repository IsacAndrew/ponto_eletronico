import re


def formatar_rg(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None

    digitos = re.sub(r"\D", "", texto)
    if len(digitos) != 9:
        raise ValueError("O RG deve conter exatamente 9 dígitos.")

    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}-{digitos[8]}"
