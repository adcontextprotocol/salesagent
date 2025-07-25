## Targeting Features

This section outlines the ad server targeting features currently supported by the ADCP Buy-Side Server and those planned for future development.

### Currently Supported

The server can currently translate abstract targeting signals from a proposal into the following concrete parameters for each supported ad server:

*   **Google Ad Manager:**
    *   `audienceSegmentIds`: Targets specific first- or third-party audience segments.
    *   `customTargeting`: Targets custom key-value pairs.
*   **Triton Digital:**
    *   `stationIds`: Targets specific audio stations.
    *   `genres`: Targets specific content genres.

### Planned Features

The following targeting capabilities are on the roadmap to provide more comprehensive and granular control over media buys.

*   **Google Ad Manager:**
    *   **Geography:** Country, region, city, and postal code.
    *   **Device:** Device category (desktop, mobile, tablet), browser, manufacturer, and model.
    *   **Inventory:** Specific ad units and placements.
    *   **Day & Time (Dayparting):** Specific days of the week and times of day.
*   **Triton Digital:**
    *   **Geography:** Country, DMA (Designated Market Area).
    *   **Device:** Device type, OS family.
    *   **Advanced Audience:** Leveraging third-party data segments for more precise audience targeting.
    *   **Contextual Targeting:** Targeting based on the content of the audio stream or podcast.