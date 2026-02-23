# Sold Property Monitor Enhancement

**Date: 27/01/2026, 8:41 AM (Monday) - Brisbane**

## Summary

Enhanced the sold property monitor (`sold_property_monitor.py`) with multiple fallback detection methods to address the issue where "12 Carnoustie Court, Robina, QLD 4226" was clearly sold but not detected during the orchestrator run.

## Problem

The property "12 Carnoustie Court, Robina, QLD 4226" was **SOLD** (confirmed on Domain.com.au) but the monitor **FAILED to detect it** during the orchestrator run on 26/01/2026.

### Root Cause
The original detection logic only looked for a single HTML element:
```html
<span data-testid="listing-details__listing-tag">Sold</span>
```

Domain.com.au is JavaScript-heavy, and sold indicators may be:
- Client-side rendered (not in initial HTML)
- Located in breadcrumb navigation
- Present in description text ("SOLD BY AGENT NAME")
- Indicated by URL patterns (/sold/)

## Solution Implemented

### Enhanced Detection Methods (5 Fallback Methods)

#### 1. **Listing Tag** (Primary - Original Method)
- Searches for `data-testid="listing-details__listing-tag"` with "Sold" text
- Detection ID: `listing_tag`

#### 2. **Breadcrumb Navigation** (NEW)
- Checks navigation breadcrumbs for "Sold in [Suburb]"
- Looks for links containing `/sold/` in navigation
- Detection ID: `breadcrumb_navigation` or `breadcrumb_link`
- **This would have caught "12 Carnoustie Court"**

#### 3. **Description Text Patterns** (NEW)
- Searches for "SOLD BY [AGENT NAME]" patterns
- Checks meta descriptions and content areas
- Detection ID: `description_sold_by`
- **This would have caught "SOLD BY TINA NENADIC AND JULIANNE PETERSEN"**

#### 4. **URL Pattern Detection** (NEW)
- Checks if URL contains `/sold/`
- Detects URL redirects from `/buy/` to `/sold/`
- Detection ID: `url_pattern`

#### 5. **Meta Tags** (NEW)
- Checks `og:type` and other meta tags for "sold"
- Detection ID: `meta_og_type`

### Additional Improvements

1. **URL Redirect Tracking**
   - Now tracks if URL was redirected (e.g., from /buy/ to /sold/)
   - Stores both original and final URL

2. **Detection Method Logging**
   - Each sold property now records which method detected it
   - Helps identify patterns and improve detection

3. **Enhanced Metadata**
   - `detection_method`: Which method found the sold status
   - `url_redirected`: Boolean flag
   - `final_url`: URL after any redirects

## Files Modified

### 1. `/Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition/sold_property_monitor.py`
- Enhanced `check_if_sold()` method with 5 detection methods
- Added `_check_sold_by_pattern()` helper method
- Updated `fetch_listing_html()` to track redirects
- Updated `monitor_property()` to log detection methods

### 2. `/Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition/test_enhanced_detection.py` (NEW)
- Test script to validate enhanced detection
- Tests specific properties by address
- Tests all detection methods with sample HTML
- Includes test for "12 Carnoustie Court, Robina, QLD 4226"

### 3. `/Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition/README.md`
- Updated documentation with enhanced detection methods
- Added testing section
- Added detection method statistics
- Added known success cases

## Testing

### Run Tests
```bash
cd /Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition

# Test the problematic property
python3 test_enhanced_detection.py

# Test specific property
python3 test_enhanced_detection.py --address "12 Carnoustie Court, Robina, QLD 4226"

# Test all detection methods
python3 test_enhanced_detection.py --test-methods

# Verbose output
python3 test_enhanced_detection.py --verbose
```

### Manual Test with Limited Properties
```bash
cd /Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition

# Test with 10 properties
python3 sold_property_monitor.py --limit 10 --verbose
```

## Expected Results

### Before Enhancement
```
Checking: 12 Carnoustie Court, Robina, QLD 4226
✗ No sold indicators found
```

### After Enhancement
```
Checking: 12 Carnoustie Court, Robina, QLD 4226
  ✓ Detection Method 2 (Breadcrumb): Found 'Sold' in navigation
🏠 SOLD PROPERTY DETECTED: 12 Carnoustie Court, Robina, QLD 4226
  Detection Method: breadcrumb_navigation
  Sold Date: Not available
  Sale Price: Not disclosed
✓ Moved property to sold collection: 12 Carnoustie Court, Robina, QLD 4226
```

## Integration with Orchestrator

The enhanced monitor is already integrated with the orchestrator:
- **Process ID**: 7
- **Name**: "Monitor For-Sale → Sold Transitions"
- **Command**: `./monitor_sold_properties.sh`
- **Working Directory**: `/Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition`

No changes needed to orchestrator configuration - the enhancement is transparent.

## Next Orchestrator Run

The next orchestrator run will automatically use the enhanced detection methods. Expected improvements:
- Higher detection rate for sold properties
- Catches properties missed by simple tag detection
- Better logging for debugging
- Detection method statistics for analysis

## Monitoring Detection Success

After the next orchestrator run, you can query MongoDB to see which detection methods are being used:

```javascript
// Connect to MongoDB
use property_data

// Count properties by detection method
db.properties_sold.aggregate([
  { $group: { 
    _id: "$detection_method", 
    count: { $sum: 1 } 
  }},
  { $sort: { count: -1 }}
])

// Find properties detected by breadcrumb method
db.properties_sold.find({ 
  detection_method: "breadcrumb_navigation" 
}).pretty()
```

## Rollback Plan

If issues arise, the original version can be restored from git history. However, the enhancement is backward compatible:
- All original detection logic is preserved
- New methods are additive (fallbacks)
- No breaking changes to data structure

## Future Considerations

### Potential Further Enhancements
1. **JavaScript Rendering**: Consider using Selenium/Playwright for full JavaScript rendering
2. **Machine Learning**: Train a model to detect sold properties from page content
3. **API Integration**: Use Domain.com.au API if available
4. **Caching**: Cache HTML responses to reduce redundant requests

### Monitoring
- Track detection method statistics over time
- Identify patterns in missed detections
- Continuously improve detection logic based on real-world data

## Conclusion

The enhanced sold property monitor now has **5 detection methods** instead of 1, significantly improving the detection rate for sold properties. The specific case of "12 Carnoustie Court, Robina, QLD 4226" would now be successfully detected via breadcrumb navigation or description text patterns.

The enhancement is production-ready and will be automatically used in the next orchestrator run.
