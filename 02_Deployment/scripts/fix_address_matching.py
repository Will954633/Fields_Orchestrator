#!/usr/bin/env python3
"""
Address Matching Fix for Sold Monitor
Last Updated: 12/02/2026, 10:20 AM (Wednesday) - Brisbane Time

Description: Fixes address matching between for-sale and master databases by implementing
robust address normalization that handles:
- Case differences (mixed case vs uppercase)
- Comma issues ("Varsity, Lakes" vs "VARSITY LAKES")
- Unit number formats ("2 36" vs "2/36")
- Extra spaces and punctuation

Target: 95%+ match rate
"""

import re

def normalize_address(address: str) -> str:
    """
    Normalize address for matching
    
    Handles:
    - Convert to uppercase
    - Remove all commas
    - Normalize spaces (multiple spaces to single)
    - Normalize unit numbers (convert "2 36" to "2/36" format)
    - Remove extra punctuation
    
    Examples:
        "27 South Bay Drive Varsity, Lakes, QLD 4227" 
        -> "27 SOUTH BAY DRIVE VARSITY LAKES QLD 4227"
        
        "1114 65 Varsity Parade Varsity, Lakes, QLD 4227"
        -> "1114/65 VARSITY PARADE VARSITY LAKES QLD 4227"
        
        "2 36 Bonogin Road, Mudgeeraba, QLD 4213"
        -> "2/36 BONOGIN ROAD MUDGEERABA QLD 4213"
    """
    if not address:
        return ""
    
    # Step 1: Convert to uppercase
    normalized = address.upper()
    
    # Step 2: Remove all commas
    normalized = normalized.replace(',', '')
    
    # Step 3: Normalize unit numbers
    # Pattern: "UNIT STREET_NUMBER STREET_NAME" -> "UNIT/STREET_NUMBER STREET_NAME"
    # Examples: "2 36 BONOGIN" -> "2/36 BONOGIN"
    #           "1114 65 VARSITY" -> "1114/65 VARSITY"
    
    # Match pattern: starts with digits, space, digits, space, then letters
    unit_pattern = r'^(\d+)\s+(\d+)\s+'
    match = re.match(unit_pattern, normalized)
    if match:
        unit = match.group(1)
        street_num = match.group(2)
        rest = normalized[match.end():]
        normalized = f"{unit}/{street_num} {rest}"
    
    # Step 4: Normalize multiple spaces to single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Step 5: Strip leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized


def addresses_match(addr1: str, addr2: str, fuzzy: bool = True) -> bool:
    """
    Check if two addresses match
    
    Args:
        addr1: First address (e.g., from for-sale database)
        addr2: Second address (e.g., from master database)
        fuzzy: If True, allows minor differences (recommended)
    
    Returns:
        True if addresses match, False otherwise
    """
    # Normalize both addresses
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)
    
    # Exact match after normalization
    if norm1 == norm2:
        return True
    
    if not fuzzy:
        return False
    
    # Fuzzy matching: check if one contains the other (for partial matches)
    # This handles cases where one address has more detail than the other
    
    # Extract key components (street number + street name)
    def extract_key_components(addr):
        # Remove postcode, state, suburb from end
        # Pattern: remove "QLD 4XXX" or similar
        addr = re.sub(r'\s+QLD\s+\d{4}$', '', addr)
        # Remove suburb name (last word before QLD)
        parts = addr.split()
        if len(parts) > 3:
            # Keep first 3-4 parts (unit/number + street name)
            return ' '.join(parts[:4])
        return addr
    
    key1 = extract_key_components(norm1)
    key2 = extract_key_components(norm2)
    
    # Check if key components match
    if key1 == key2:
        return True
    
    # Check if one is substring of other (handles extra details)
    if key1 in key2 or key2 in key1:
        return True
    
    return False


def test_address_matching():
    """Test the address matching function with real examples"""
    
    print("=" * 80)
    print("ADDRESS MATCHING TESTS")
    print("=" * 80)
    print()
    
    # Test cases from real data
    test_cases = [
        # (for_sale_address, master_address, should_match)
        ("27 South Bay Drive Varsity, Lakes, QLD 4227", "27 SOUTH BAY DRIVE VARSITY LAKES QLD 4227", True),
        ("73 Azzurra Drive Varsity, Lakes, QLD 4227", "73 AZZURRA DRIVE VARSITY LAKES QLD 4227", True),
        ("20 Swagman Court, Mudgeeraba, QLD 4213", "20 SWAGMAN COURT MUDGEERABA QLD 4213", True),
        ("1 2 Pappas Way, Carrara, QLD 4211", "1/2 PAPPAS WAY CARRARA QLD 4211", True),
        ("11 Woolmere Street, Carrara, QLD 4211", "11 WOOLMERE STREET CARRARA QLD 4211", True),
        ("5 Fulham Place, Robina, QLD 4226", "5 FULHAM PLACE ROBINA QLD 4226", True),
        ("1114 65 Varsity Parade Varsity, Lakes, QLD 4227", "1114/65 VARSITY PARADE VARSITY LAKES QLD 4227", True),
        ("2 36 Bonogin Road, Mudgeeraba, QLD 4213", "2/36 BONOGIN ROAD MUDGEERABA QLD 4213", True),
        # Should NOT match
        ("27 South Bay Drive Varsity, Lakes, QLD 4227", "28 SOUTH BAY DRIVE VARSITY LAKES QLD 4227", False),
        ("20 Swagman Court, Mudgeeraba, QLD 4213", "20 SWAGMAN STREET MUDGEERABA QLD 4213", False),
    ]
    
    passed = 0
    failed = 0
    
    for i, (addr1, addr2, expected) in enumerate(test_cases, 1):
        result = addresses_match(addr1, addr2)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"Test {i}: {status}")
        print(f"  For-Sale: {addr1}")
        print(f"  Master:   {addr2}")
        print(f"  Normalized 1: {normalize_address(addr1)}")
        print(f"  Normalized 2: {normalize_address(addr2)}")
        print(f"  Expected: {expected}, Got: {result}")
        print()
    
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed ({passed/(passed+failed)*100:.1f}% success rate)")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = test_address_matching()
    exit(0 if success else 1)
