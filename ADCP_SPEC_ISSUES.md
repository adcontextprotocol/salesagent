# AdCP Specification Clarification Needs

Based on implementation experience with the A2A protocol integration, the following areas of the AdCP specification need clarification:

## 1. Product Field Requirements

**Issue:** The spec is unclear about which product fields are mandatory vs optional.

**Current Ambiguity:**
- Some products may not have `price_model` or `price_guidance` (e.g., bonus inventory)
- `delivery_method` might not apply to all product types
- `targeting_template` could be empty for run-of-site products

**Recommendation:** 
Define a minimal required set of fields and explicitly mark others as optional with clear semantics for null/missing values.

## 2. Price Guidance Structure

**Issue:** The structure of `price_guidance` when pricing is not available or not applicable is unclear.

**Current Implementation Variations:**
```json
// Option 1: null
"price_guidance": null

// Option 2: Empty object
"price_guidance": {}

// Option 3: Explicit unavailable flag
"price_guidance": {
  "available": false,
  "reason": "negotiated_rates"
}
```

**Recommendation:** 
Standardize the response format for unavailable pricing information.

## 3. Message/Send Response Format

**Issue:** Should `message/send` always return structured data parts for entity queries, or is text-only acceptable?

**Example Scenarios:**
- User asks "Show me sports inventory" - Should return both text summary AND data part with products
- User asks "How do I create a campaign?" - Text-only response is appropriate
- User asks "What's the status of MB-123?" - Should this include structured status data?

**Recommendation:** 
Define clear rules for when structured data parts are required vs optional in message responses.

## 4. Targeting Capabilities Structure

**Issue:** The spec doesn't clearly define which targeting dimensions are mandatory vs optional.

**Questions:**
- Must all systems support geo, device, audience, and content targeting?
- How should systems report partially-supported dimensions?
- What's the format for custom/proprietary targeting options?

**Recommendation:** 
Define a core set of required targeting capabilities and a standard way to report custom extensions.

## 5. Task Response Consistency

**Issue:** The A2A protocol expects all operations to return Task objects, but some operations feel more natural as direct responses.

**Examples:**
- `get_messages` - Returns a list, not really a "task"
- `clear_context` - Simple acknowledgment, full Task structure seems excessive

**Recommendation:** 
Clarify which operations should return Task objects vs simpler response formats.

## 6. Creative Format Specifications

**Issue:** The level of detail required in format specifications is unclear.

**Questions:**
- Should `assets` always be populated or can it be empty?
- How detailed should `delivery_options` be?
- Are mime_types required for all format types?

**Example:**
```json
{
  "format_id": "video_16x9",
  "assets": [],  // Is this valid?
  "delivery_options": {
    "vast": {
      "versions": ["3.0", "4.0"]  // Required level of detail?
    }
  }
}
```

**Recommendation:** 
Provide complete examples for each media type with required vs optional fields clearly marked.

## 7. Error Response Standardization

**Issue:** Error responses vary between protocol implementations.

**Current Variations:**
- MCP: Exceptions with error messages
- A2A: Task with failed status and error field
- HTTP: Status codes with JSON error bodies

**Recommendation:** 
Define a unified error model that can be mapped to different protocol requirements.

## 8. Context and State Management

**Issue:** The relationship between context_id, message history, and task state is unclear.

**Questions:**
- Should context persist across sessions?
- How long should message history be retained?
- Can multiple tasks share the same context?

**Recommendation:** 
Define clear semantics for context lifecycle and state management.

## 9. Authentication and Principal Identification

**Issue:** The spec doesn't clearly define how principals are identified across different protocols.

**Current Implementation:**
- Using `x-adcp-auth` header for both MCP and A2A
- Principal ID extracted from token
- Tenant routing via subdomain or header

**Recommendation:** 
Standardize authentication and principal identification across all protocol bindings.

## 10. Batch Operations

**Issue:** Support for batch operations is inconsistent.

**Questions:**
- Should batch create/update be supported?
- How should partial failures be reported?
- What's the maximum batch size?

**Recommendation:** 
Define standard patterns for batch operations if supported.

## Proposed Solutions

1. **Create a formal JSON Schema** for all data types with required/optional field annotations
2. **Add a conformance test suite** that validates implementations
3. **Provide reference implementations** for each protocol binding
4. **Version the spec** to allow for backwards-compatible evolution
5. **Create a decision log** documenting design choices and rationale

## Next Steps

1. File these as separate issues in the AdCP specification repository
2. Work with the spec maintainers to resolve ambiguities
3. Update our implementation based on clarifications
4. Contribute test cases to help other implementers