# Japan source integration research

The user clarified that JACC should connect to Japan vehicle websites rather than use a static local catalog.

## Candidate sources reviewed

**SBT Japan Chassis Check** provides a public form that accepts a Japanese frame/chassis number and a maker selection. Its page states that the result is a reference-only manufacturing-year lookup and does not guarantee the information. The supported makers shown on the page are Toyota, Nissan, Mitsubishi, Honda, Mazda, Subaru, Suzuki, Isuzu, and Daihatsu. The form was tested with `AGH30-0015779`; the input was accepted, but the maker had not yet been selected, so no result was submitted.

**Real Motor Japan** exposes a chassis-code catalog organized by make and chassis code. Its catalog content advertises engine displacement, manufacture-year decoding, and shipping dimensions, which is closer to JACC's desired specification card but appears to be a catalog website rather than an openly documented API.

**EPC-data** provides Japanese parts catalogs for Toyota, Nissan, Mitsubishi, Honda, and Lexus with frame-number inputs. It is designed primarily for parts lookup, not a general vehicle specification API, so automated use would require checking its terms and technical access before integration.

**CAR VX** explains the difference between Japanese chassis/frame numbers and VINs, and states that a frame number alone contains less information than a VIN; Japanese domestic vehicles also use a model code for feature combinations. This supports treating chassis-prefix decoding as a model-level reference rather than an exact trim or auction-condition result.

## Important integration conclusion

JACC should not scrape multiple Japan websites directly from the public frontend. The safer design is a Railway backend adapter that calls one approved source or licensed API, normalizes its response, applies timeout/rate-limit/error handling, and returns only the fields required by the JACC frontend. Source terms, robots rules, authentication requirements, and response stability must be verified before production use. If no source grants stable automated access, use a licensed data/API provider or a controlled server-side reference database instead of browser scraping.

## Sources

- https://www.sbtjapan.com/support/vehicle_inspection/chassis-check
- https://www.realmotor.jp/catalog
- https://www.epc-data.com/
- https://carvx.jp/chassis-number

## Interactive source checks

The SBT form submits to `/support/vehicle_inspection/chassis-check/search?number=AGH30-0015779&maker=2` when Toyota is selected. The browser response did not provide a usable result page in this session and fell back to a blank page, so the endpoint should not be treated as a stable integration API without permission and further server-side testing.

Goo-net's public Japanese catalog page for `DBA-AGH30W` lists multiple grades and demonstrates the exact fields JACC needs: 2,493 cc, CVT, FF, 7 or 8 seats, fuel economy, and grade-specific pricing. The page is a catalog/detail website with Japanese HTML rather than a documented public API. It is a strong reference source for manual validation, but automated extraction requires checking terms, robots rules, rate limits, and response stability first.

- https://www.goo-net.com/car/TOYOTA/ALPHARD/DBA-AGH30W.html

## SBT access constraints

SBT's Terms of Use state that site content is copyrighted and that reproduction or use of site content is prohibited; the site content is also provided without a warranty of completeness or accuracy. Therefore, a JACC server-side scraper should not be built against SBT without written permission. SBT's `robots.txt` currently disallows CSV paths, used-car search paths, login/signup, and photo-list paths; it does not explicitly disallow the chassis-check path, but robots permission alone does not override the Terms of Use.

- https://www.sbtjapan.com/policy/terms
- https://www.sbtjapan.com/robots.txt

## Real Motor access constraints

Real Motor's Terms of Use state that the service is free unless otherwise stated, but the service and original content remain the company's property. Written content, photos, video, and other site content may only be viewed in the prescribed methods; copying, redistributing, reusing, changing, or creating derivative works is prohibited unless otherwise stated. This means the catalog can be used as a human-facing reference link, but free automated reuse inside JACC should not be implemented without permission.

Real Motor's `robots.txt` blocks selected stock filter parameters and `/map/`, but does not explicitly disallow `/catalog`. This is not sufficient authorization to scrape catalog content because the Terms still restrict copying and reuse.

- https://www.realmotor.jp/terms-of-use
- https://www.realmotor.jp/robots.txt

## TS Export / Drom decoder discovery

TS Export presents a free JDM decoder UI, but its form submits a GET request to `https://www.drom.ru/frameno/common.php` rather than to a TS Export-owned API. The form field is `no` for the chassis number and `firm` for the maker code. The page states that Japanese chassis numbers are sequential and that decoder results are best-available information, not guaranteed build dates. The Drom endpoint may be technically usable for a free prototype, but its terms, rate limits, response format, and permission for server-side reuse must be checked before JACC calls it.

- https://www.ts-export.com/page.php?page=about_vin_decoders
- https://www.drom.ru/frameno/common.php

## Drom decoder access constraints

Drom's portal rules state that portal information is for personal, non-commercial use. Reproduction or use requires written permission, automated extraction is prohibited without written permission, and extraction/collection/processing/copying/redistribution is strictly prohibited. The free Frameno endpoint technically returns a useful build month for some chassis numbers, but it returned `AGH30-0015779 not found` and requires a referrer in this environment. Therefore it must not be connected to JACC as an automated backend source without written permission.

Drom's robots file contains extensive path/query restrictions; regardless of whether `/frameno/` is explicitly blocked in a given section, the portal rules prohibit automated extraction without permission.

- https://www.drom.ru/about/reprint/
- https://www.drom.ru/robots.txt

## JACC source-link prototype test

The feature branch adds a `Japan Source Check` card after chassis lookup. For `AGH30-0015779` with a representative ALPHARD Sheet record, the browser test confirmed five source buttons, a copy-chassis button, and preservation of the existing Sheet record price. The ALPHARD model also resolves to the Goo-net Alphard catalog landing page. The source buttons open external pages only; JACC does not fetch or copy their content.

A second local browser test used an unknown chassis `ZZZ99-1234567` with no Sheet records. The `Japan Source Check` card still rendered five source buttons and the copy button while the normal `not found in records` message remained. This confirms source links are independent of JACC Sheet data availability.
