"""Software Bill of Materials (SBOM) generator — CycloneDX and SPDX output.

Generates SBOM from installed packages and LARGESTACK dependencies.
Required for enterprise procurement and CISA 2025 minimum elements.

Usage:
    sbom = SBOMGenerator()
    sbom.generate("cyclonedx", output_path="sbom.json")
    sbom.generate("spdx", output_path="sbom.spdx.json")
"""
from __future__ import annotations
import importlib.metadata, json, logging, os, platform, time, uuid
from typing import Any

log = logging.getLogger("largestack.security.sbom")


class SBOMGenerator:
    """Generate Software Bill of Materials in CycloneDX or SPDX format."""
    
    LARGESTACK_DIRECT_DEPS = [
        "pydantic", "httpx", "fastapi", "uvicorn", "click", "pyyaml",
        "opentelemetry-api", "opentelemetry-sdk",
    ]
    
    LARGESTACK_OPTIONAL_DEPS = {
        "ml": ["detoxify", "transformers", "torch", "sentence-transformers"],
        "security": ["cryptography", "pyjwt"],
        "database": ["psycopg2-binary", "psycopg"],
        "rag": ["presidio-analyzer", "presidio-anonymizer", "spacy"],
        "cloud": ["boto3", "hvac"],
    }
    
    def __init__(self, package_name: str = "largestack", version: str = "0.1.1"):
        self.package_name = package_name
        self.version = version
    
    def generate(self, format: str = "cyclonedx", output_path: str = None,
                 include_transitive: bool = True) -> dict:
        """Generate SBOM. format: 'cyclonedx' or 'spdx'."""
        packages = self._collect_packages(include_transitive)
        
        if format == "cyclonedx":
            sbom = self._generate_cyclonedx(packages)
        elif format == "spdx":
            sbom = self._generate_spdx(packages)
        else:
            raise ValueError(f"Format must be 'cyclonedx' or 'spdx', got: {format}")
        
        if output_path:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(sbom, f, indent=2)
            log.info(f"SBOM written to {output_path} ({len(packages)} components)")
        
        return sbom
    
    def _collect_packages(self, include_transitive: bool) -> list[dict]:
        """Collect installed package metadata."""
        packages = []
        seen = set()
        
        for dist in importlib.metadata.distributions():
            name = dist.metadata["Name"]
            if name in seen:
                continue
            seen.add(name)
            
            version = dist.metadata["Version"] or "unknown"
            license_info = dist.metadata.get("License", dist.metadata.get("License-Expression", ""))
            author = dist.metadata.get("Author", dist.metadata.get("Author-email", ""))
            homepage = dist.metadata.get("Home-page", "")
            
            # Classify relationship to LARGESTACK
            is_direct = name.lower().replace("-", "_") in [d.replace("-", "_") for d in self.LARGESTACK_DIRECT_DEPS]
            is_optional = any(
                name.lower().replace("-", "_") in [d.replace("-", "_") for d in deps]
                for deps in self.LARGESTACK_OPTIONAL_DEPS.values()
            )
            
            if not include_transitive and not is_direct and not is_optional:
                continue
            
            packages.append({
                "name": name,
                "version": version,
                "license": license_info[:200] if license_info else "",
                "author": author[:200] if author else "",
                "homepage": homepage,
                "relationship": "direct" if is_direct else ("optional" if is_optional else "transitive"),
                "purl": f"pkg:pypi/{name.lower()}@{version}",
            })
        
        packages.sort(key=lambda p: p["name"].lower())
        return packages
    
    def _generate_cyclonedx(self, packages: list[dict]) -> dict:
        """Generate CycloneDX 1.5 format SBOM."""
        components = []
        for pkg in packages:
            component = {
                "type": "library",
                "name": pkg["name"],
                "version": pkg["version"],
                "purl": pkg["purl"],
                "bom-ref": pkg["purl"],
            }
            if pkg["license"]:
                component["licenses"] = [{"license": {"name": pkg["license"][:100]}}]
            if pkg["author"]:
                component["author"] = pkg["author"][:100]
            if pkg["homepage"]:
                component["externalReferences"] = [
                    {"type": "website", "url": pkg["homepage"]}
                ]
            components.append(component)
        
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tools": [{"name": "largestack-sbom", "version": self.version}],
                "component": {
                    "type": "application",
                    "name": self.package_name,
                    "version": self.version,
                    "purl": f"pkg:pypi/{self.package_name}@{self.version}",
                },
                "properties": [
                    {"name": "python:version", "value": platform.python_version()},
                    {"name": "os:name", "value": platform.system()},
                ],
            },
            "components": components,
        }
    
    def _generate_spdx(self, packages: list[dict]) -> dict:
        """Generate SPDX 2.3 format SBOM."""
        spdx_packages = []
        for i, pkg in enumerate(packages):
            spdx_pkg = {
                "SPDXID": f"SPDXRef-Package-{i+1}",
                "name": pkg["name"],
                "versionInfo": pkg["version"],
                "downloadLocation": pkg["homepage"] or "NOASSERTION",
                "filesAnalyzed": False,
                "supplier": f"Person: {pkg['author']}" if pkg["author"] else "NOASSERTION",
            }
            if pkg["license"]:
                spdx_pkg["licenseConcluded"] = pkg["license"][:100]
                spdx_pkg["licenseDeclared"] = pkg["license"][:100]
            else:
                spdx_pkg["licenseConcluded"] = "NOASSERTION"
                spdx_pkg["licenseDeclared"] = "NOASSERTION"
            
            spdx_pkg["externalRefs"] = [{
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": pkg["purl"],
            }]
            spdx_packages.append(spdx_pkg)
        
        relationships = [{
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relatedSpdxElement": f"SPDXRef-Package-{i+1}",
            "relationshipType": "DEPENDS_ON" if pkg["relationship"] == "direct" else "DEV_DEPENDENCY_OF",
        } for i, pkg in enumerate(packages)]
        
        return {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": self.package_name,
            "documentNamespace": f"https://rivailabs.com/sbom/{self.package_name}/{self.version}/{uuid.uuid4()}",
            "creationInfo": {
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "creators": [f"Tool: largestack-sbom-{self.version}"],
            },
            "packages": spdx_packages,
            "relationships": relationships,
        }
    
    @property
    def summary(self) -> dict:
        """Quick summary without full SBOM generation."""
        pkgs = self._collect_packages(include_transitive=False)
        return {
            "direct_deps": sum(1 for p in pkgs if p["relationship"] == "direct"),
            "optional_deps": sum(1 for p in pkgs if p["relationship"] == "optional"),
            "formats_supported": ["cyclonedx", "spdx"],
        }
