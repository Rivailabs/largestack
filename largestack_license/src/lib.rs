//! LARGESTACK Agentic AI License Validation — Ed25519 signature verification.
//! Compiled via PyO3 as abi3 wheel (one wheel for Python 3.9+).
//!
//! Build: maturin build --release
//! Test:  cargo test

use pyo3::prelude::*;
use ed25519_dalek::{VerifyingKey, Signature, Verifier};
use sha2::{Sha256, Digest};

/// Ed25519 public key for license verification.
/// Generate keypair: openssl genpkey -algorithm ed25519 -out private.pem
/// Extract pubkey bytes and paste here.
/// PRODUCTION Ed25519 public key — generated 2026-04-14.
/// Generate: openssl genpkey -algorithm ed25519 -out private.pem
/// Extract:  openssl pkey -in private.pem -pubout -outform DER | tail -c 32 | xxd -p
const PUBLIC_KEY_HEX: &str = "a9f64413bb5a70c9828cff7f53a317d8db98d0c040dede571254ae2b207ab9f7";

/// Validate a LARGESTACK Agentic AI license.
/// 
/// Args:
///     license_data: The license payload (JSON bytes)
///     signature_hex: The Ed25519 signature as hex string
///
/// Returns:
///     True if signature is valid, False otherwise
#[pyfunction]
fn validate_license(license_data: &[u8], signature_hex: &str) -> PyResult<bool> {
    // Decode public key
    let pk_bytes = hex::decode(PUBLIC_KEY_HEX)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid public key hex: {}", e)))?;
    
    if pk_bytes.len() != 32 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Public key must be 32 bytes"));
    }
    
    let mut pk_array = [0u8; 32];
    pk_array.copy_from_slice(&pk_bytes);
    
    let public_key = VerifyingKey::from_bytes(&pk_array)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid public key: {}", e)))?;
    
    // Decode signature
    let sig_bytes = hex::decode(signature_hex)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid signature hex: {}", e)))?;
    
    let signature = Signature::from_slice(&sig_bytes)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid signature: {}", e)))?;
    
    Ok(public_key.verify(license_data, &signature).is_ok())
}

/// Generate machine fingerprint via SHA-256 of system identifiers.
#[pyfunction]
fn machine_fingerprint() -> String {
    let mut hasher = Sha256::new();
    hasher.update(std::env::consts::OS.as_bytes());
    hasher.update(std::env::consts::ARCH.as_bytes());
    
    // Linux machine-id
    if let Ok(id) = std::fs::read_to_string("/etc/machine-id") {
        hasher.update(id.trim().as_bytes());
    }
    // macOS hardware UUID
    if let Ok(output) = std::process::Command::new("ioreg")
        .args(["-rd1", "-c", "IOPlatformExpertDevice"])
        .output() {
        hasher.update(&output.stdout);
    }
    
    let result = hasher.finalize();
    hex::encode(&result[..16])
}

/// Python module
#[pymodule]
fn largestack_license(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(validate_license, m)?)?;
    m.add_function(wrap_pyfunction!(machine_fingerprint, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_fingerprint() {
        let fp = machine_fingerprint();
        assert_eq!(fp.len(), 32);
    }
    
    #[test]
    fn test_invalid_signature() {
        // Dev key — verify that random signatures are rejected
        let result = validate_license(b"test", "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000");
        // Should return Ok(false) — signature doesn't verify
        assert!(result.is_ok());
        assert!(!result.unwrap());
    }
}
