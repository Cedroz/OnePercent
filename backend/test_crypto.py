from crypto import encrypt_token, decrypt_token


# Encrypting then decrypting must return the exact original string — otherwise
# stored GitHub tokens would come back garbled and every API call would break.
def test_encrypt_decrypt_round_trip():
    original = "gho_secretGitHubToken123"
    encrypted = encrypt_token(original)
    decrypted = decrypt_token(encrypted)
    assert decrypted == original


# The encrypted output must differ from the plain text (proves it actually scrambles).
def test_encrypt_changes_the_text():
    original = "gho_secretGitHubToken123"
    encrypted = encrypt_token(original)
    assert original != encrypted
