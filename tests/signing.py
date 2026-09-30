"""A digitally signed PDF for tests, signed and checked with pyHanko.

A throwaway self-signed certificate is made each time; validation trusts it
explicitly, so "valid" means the signature still covers the bytes it signed.
"""
from __future__ import annotations

import datetime
import io


def _certificate():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CalcForge test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
                                         key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, key_cert_sign=True,
                                         crl_sign=False, encipher_only=False,
                                         decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    return (key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()),
            cert.public_bytes(serialization.Encoding.PEM))


def signed_pdf(path: str, unsigned: bytes) -> bytes:
    """Sign *unsigned* (PDF bytes), write it to *path*, and return the bytes."""
    from pyhanko.sign import signers
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    key_pem, cert_pem = _certificate()
    signer = signers.SimpleSigner.load_from_pem_bytes(key_pem, cert_pem) \
        if hasattr(signers.SimpleSigner, "load_from_pem_bytes") else None
    if signer is None:
        import tempfile
        import os
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "k.pem"), "wb") as out:
            out.write(key_pem)
        with open(os.path.join(folder, "c.pem"), "wb") as out:
            out.write(cert_pem)
        signer = signers.SimpleSigner.load(os.path.join(folder, "k.pem"),
                                           os.path.join(folder, "c.pem"))
    writer = IncrementalPdfFileWriter(io.BytesIO(unsigned))
    out = signers.sign_pdf(writer, signers.PdfSignatureMetadata(field_name="Signature1"),
                           signer=signer)
    data = out.getvalue()
    with open(path, "wb") as handle:
        handle.write(data)
    signed_pdf.certificate = cert_pem
    return data


def signature_is_intact(path: str) -> bool:
    """Whether the file's first signature still covers what it signed."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext
    from asn1crypto import pem, x509 as asn1x509

    _t, _h, der = pem.unarmor(signed_pdf.certificate)
    context = ValidationContext(trust_roots=[asn1x509.Certificate.load(der)])
    with open(path, "rb") as handle:
        reader = PdfFileReader(handle)
        status = validate_pdf_signature(reader.embedded_signatures[0], context)
        return bool(status.intact and status.valid)
