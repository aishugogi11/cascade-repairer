# Sabre API Notes — Phase 6

Research date: 2026-07-08, against the live portal (developer.sabre.com) and
Sabre's official Postman collections (SabreDevStudio/postman-collections;
Booking Management v2026.04, Lodging v2025.09, both with saved CERT
responses). The old `/docs/rest_apis/...` URL scheme is retired; current doc
pages live under `/rest-api/...`. Payloads below are trimmed to the fields
the mock layer models; `backend/api/sabre/shapes.py` matches them 1:1.

Confidence: endpoints, auth, hotel book/cancel responses, and the modify-dates
flow are verified against live pages or saved CERT responses. The air
createBooking response example is composed from the verified request schema +
the verified hotel response wrapper (medium-high). The v2 secret construction
recipe is corroborated but its guide page is JS-walled (medium-high).

## Environments & auth

| Environment | REST base URL |
|---|---|
| CERT (test) | `https://api.cert.platform.sabre.com` |
| Production | `https://api.platform.sabre.com` |

`POST /v2/auth/token`, `grant_type=client_credentials`, header
`Authorization: Basic {secret}` where the secret is
`base64( base64("V1:{EPR}:{PCC}:AA") + ":" + base64(password) )`.
(A newer `POST /v3/auth/token` uses a password grant with username
`{EPR}-{PCC}-AA`.) Response:

```json
{ "access_token": "T1RLAQK...", "token_type": "bearer", "expires_in": 604800 }
```

`expires_in` 604800s = 7 days; refresh on 401 rather than trusting the
lifetime. Every operation below sends `Authorization: Bearer {access_token}`
and `Content-Type: application/json`. Booking Management endpoints are
stateless and accept sessionless tokens.

## 1. Flight search — Bargain Finder Max v5

`POST /v5/offers/shop` (v3/v4 still live; Sabre supports ~5 concurrent
versions). Request root `OTA_AirLowFareSearchRQ`:

```json
{
  "OTA_AirLowFareSearchRQ": {
    "Version": "5",
    "POS": {
      "Source": [{
        "PseudoCityCode": "XXXX",
        "RequestorID": { "Type": "1", "ID": "1", "CompanyName": { "Code": "TN" } }
      }]
    },
    "OriginDestinationInformation": [{
      "RPH": "1",
      "DepartureDateTime": "2026-07-17T08:00:00",
      "OriginLocation": { "LocationCode": "MSP" },
      "DestinationLocation": { "LocationCode": "SFO" }
    }],
    "TravelPreferences": { "MaxStopsQuantity": 0 },
    "TravelerInfoSummary": {
      "AirTravelerAvail": [{
        "PassengerTypeQuantity": [{ "Code": "ADT", "Quantity": 1 }]
      }]
    },
    "TPA_Extensions": {
      "IntelliSellTransaction": { "RequestType": { "Name": "50ITINS" } }
    }
  }
}
```

Response root `groupedItineraryResponse` (GIR). Itineraries reference legs by
id (`legs[].ref` → `legDescs[].id`), legs reference schedules
(`schedules[].ref` → `scheduleDescs[].id`):

```json
{
  "groupedItineraryResponse": {
    "version": "5",
    "statistics": { "itineraryCount": 1 },
    "scheduleDescs": [{
      "id": 1,
      "stopCount": 0,
      "eTicketable": true,
      "elapsedTime": 245,
      "departure": { "airport": "MSP", "city": "MSP", "country": "US", "time": "08:00:00-05:00" },
      "arrival":   { "airport": "SFO", "city": "SFO", "country": "US", "time": "10:05:00-07:00" },
      "carrier": {
        "marketing": "AA", "marketingFlightNumber": 576,
        "operating": "AA", "operatingFlightNumber": 576,
        "equipment": { "code": "E75" }
      }
    }],
    "legDescs": [{ "id": 1, "elapsedTime": 245, "schedules": [{ "ref": 1 }] }],
    "itineraryGroups": [{
      "groupDescription": {
        "legDescriptions": [{
          "departureDate": "2026-07-17",
          "departureLocation": "MSP",
          "arrivalLocation": "SFO"
        }]
      },
      "itineraries": [{
        "id": 1,
        "legs": [{ "ref": 1 }],
        "pricingInformation": [{
          "fare": {
            "validatingCarrierCode": "AA",
            "totalFare": {
              "totalPrice": 187.6, "currency": "USD",
              "baseFareAmount": 143.0, "totalTaxAmount": 44.6
            }
          }
        }]
      }]
    }]
  }
}
```

NDC content additionally returns `offerId`/`offerItemId`, which must be
revalidated with `POST /v1/offers/price` before booking. Out of scope for the
mock layer (ATPCO shapes only).

## 2. Flight booking — Create Booking

`POST /v1/trip/orders/createBooking` — one unified service for air, hotel,
and car. Traditional (ATPCO) air passes `flightDetails`; an empty object in
`flightPricing` means "price at booking with defaults". `flightStatusCode`
"NN" = need/sell.

```json
{
  "travelers": [
    { "givenName": "Josh", "surname": "Janzen", "birthDate": "1980-01-01", "passengerCode": "ADT" }
  ],
  "contactInfo": { "emails": ["demo@example.com"], "phones": ["+16125550100"] },
  "flightDetails": {
    "flights": [{
      "flightNumber": 576,
      "airlineCode": "AA",
      "fromAirportCode": "MSP",
      "toAirportCode": "SFO",
      "departureDate": "2026-07-17",
      "departureTime": "08:00",
      "bookingClass": "Y",
      "flightStatusCode": "NN"
    }],
    "flightPricing": [{}]
  }
}
```

Response wrapper (verified from a real saved CERT createBooking response):
`timestamp` + `confirmationId` + `booking`, where `booking` has the same
structure as Get Booking. Top-level `confirmationId` is the **Sabre record
locator (PNR)**; `flights[].confirmationId` is the **airline record locator**;
`flights[].itemId` is the segment item id that cancel/modify calls target.

```json
{
  "timestamp": "2026-07-08T20:17:30",
  "confirmationId": "GLEBNY",
  "booking": {
    "bookingId": "GLEBNY",
    "startDate": "2026-07-17",
    "endDate": "2026-07-19",
    "isCancelable": true,
    "isTicketed": false,
    "travelers": [
      { "givenName": "JOSH", "surname": "JANZEN", "type": "ADULT", "passengerCode": "ADT", "nameAssociationId": "1" }
    ],
    "flights": [{
      "itemId": "12",
      "confirmationId": "NIEBNY",
      "flightNumber": 576,
      "airlineCode": "AA",
      "fromAirportCode": "MSP",
      "toAirportCode": "SFO",
      "departureDate": "2026-07-17",
      "departureTime": "08:00",
      "cabinTypeName": "ECONOMY",
      "flightStatusName": "Confirmed"
    }],
    "payments": {
      "flightTotals": [
        { "subtotal": "143.00", "taxes": "44.60", "total": "187.60", "currencyCode": "USD" }
      ]
    }
  }
}
```

Ticket issuance is a separate call (`POST /v1/trip/orders/fulfillFlightTickets`),
not needed for the demo shapes.

## 3. Flight cancel — Cancel Booking

`POST /v1/trip/orders/cancelBooking`. Cancel everything (`cancelAll`) or
selected items by `itemId` (`"flights": [{ "itemId": "12" }]`).
`errorHandlingPolicy`: `HALT_ON_ERROR` (default) or `ALLOW_PARTIAL_CANCEL`.

```json
{
  "confirmationId": "GLEBNY",
  "retrieveBooking": true,
  "cancelAll": true,
  "errorHandlingPolicy": "ALLOW_PARTIAL_CANCEL"
}
```

Response (real saved CERT response): with `retrieveBooking: true` the
post-cancel state of the booking comes back, cancelled segments removed.

```json
{
  "timestamp": "2026-07-08T20:20:08",
  "booking": {
    "bookingId": "GLEBNY",
    "travelers": [
      { "givenName": "JOSH", "surname": "JANZEN", "type": "ADULT", "passengerCode": "ADT", "nameAssociationId": "1" }
    ]
  }
}
```

## 4. Flight rebook — cancel + create (no single REST endpoint)

There is no one-call REST "rebook". Modify Booking explicitly does **not**
change flight segments. The documented paths:

- **Unticketed booking (the demo case):** `getBooking` → `cancelBooking` (the
  flight `itemId`s) → `createBooking` with the new flights. This is the
  sequence Sabre's own workflow collections use for date changes on
  unticketed PNRs, and it is what `rebook_flight` composes internally: the
  rebook request/response shapes are the §3 cancel + §2 create shapes, and
  the operation's result is the new booking's create response.
- **Ticketed ATPCO booking (true exchange, not modeled this phase):**
  `POST /v1/offers/flightReshop` (beta, ATPCO only) shops exchange offers
  with the fare difference, then `POST /v1.0.0/exchange/booking`
  (`ExchangeBookingRQ`) cancels, rebooks, and commits the Price Quote Reissue
  in one transaction; `POST /v1/trip/orders/checkFlightTickets` verifies
  exchangeability first. Documented here for event-day reference; the demo
  seeds unticketed bookings so the cancel+create path is the honest one.

## 5. Hotel booking — Create Booking (CSL)

Same `POST /v1/trip/orders/createBooking`, hotel element. Legacy GDS hotel
content is blocked (CSL only). Booking requires a `bookingKey` from the shop
chain: `POST /v5/get/hotelavail` → `POST /v5/hotel/pricecheck` (root
`HotelPriceCheckRQ`; response `HotelPriceCheckRS.PriceCheckInfo.BookingKey`,
a UUID, plus `PriceChange` boolean).

```json
{
  "travelers": [{ "givenName": "JOSH", "surname": "JANZEN", "passengerCode": "ADT" }],
  "contactInfo": { "emails": ["demo@example.com"], "phones": ["+16125550100"] },
  "hotel": {
    "useCsl": true,
    "bookingKey": "6f0a79e3-2fb4-4305-92c7-00f138ed29a9",
    "rooms": [{ "travelerIndices": [1] }],
    "paymentPolicy": "GUARANTEE",
    "formOfPayment": 1
  },
  "payment": {
    "formsOfPayment": [{
      "type": "PAYMENTCARD",
      "cardTypeCode": "VI",
      "cardNumber": "4111111111111111",
      "expiryDate": "2027-10"
    }]
  }
}
```

`hotel.formOfPayment` is a 1-based index into `payment.formsOfPayment`.
Response (trimmed from a real saved CERT 200): same wrapper as §2. Top-level
`confirmationId` = Sabre PNR; `hotels[].confirmationId` = hotel supplier
confirmation; `hotelStatusCode` "HK" = confirmed; `hotels[].itemId` is what
the date-change call targets.

```json
{
  "timestamp": "2026-07-08T20:17:30",
  "confirmationId": "UEEBMH",
  "booking": {
    "bookingId": "UEEBMH",
    "startDate": "2026-07-17",
    "endDate": "2026-07-19",
    "isCancelable": true,
    "isTicketed": false,
    "travelers": [
      { "givenName": "JOSH", "surname": "JANZEN", "type": "ADULT", "passengerCode": "ADT", "nameAssociationId": "1" }
    ],
    "hotels": [{
      "itemId": "32",
      "confirmationId": "3322102014-",
      "hotelName": "TRU BY HILTON MOUNTAIN VIEW",
      "checkInDate": "2026-07-17",
      "checkOutDate": "2026-07-19",
      "leadTravelerIndex": 1,
      "room": {
        "roomType": "Guest Room",
        "quantity": 1,
        "productCode": "A05LV0",
        "roomRate": { "amount": "179.00", "currencyCode": "USD" },
        "travelerIndices": [1]
      },
      "isRefundable": true,
      "hotelStatusCode": "HK",
      "hotelStatusName": "Confirmed",
      "chainCode": "RU",
      "propertyId": "102114737",
      "paymentPolicy": "GUARANTEE",
      "payment": { "subtotal": "365.16", "taxes": "60.86", "fees": "7.16", "total": "426.02", "currencyCode": "USD" },
      "numberOfGuests": 2
    }],
    "payments": {
      "hotelTotals": [
        { "subtotal": "365.16", "taxes": "60.86", "fees": "7.16", "total": "426.02", "currencyCode": "USD" }
      ]
    }
  }
}
```

## 6. Hotel date change — Modify Booking

`POST /v1/trip/orders/modifyBooking`. Check-in/checkout date modification is
explicitly supported for CSL hotels. Mandatory optimistic-locking flow:

1. `POST /v1/trip/orders/getBooking` `{"confirmationId": "UEEBMH"}` (without
   `returnOnly`) — yields the current `bookingSignature` and the hotel
   `itemId`.
2. Only if the new dates fall outside the originally shopped range: re-shop
   (`/v5/get/hotelavail` → `/v5/hotel/pricecheck`) and pass the new
   `bookingKey` inside the `after.hotels[]` item. In-range changes skip this.
3. `POST /v1/trip/orders/modifyBooking` with `before`/`after` states (Sabre's
   own date-change samples send an empty `before`):

```json
{
  "bookingSignature": "d64eb4d0efb0043ebd8a2b3nlxvz...",
  "confirmationId": "UEEBMH",
  "before": {},
  "after": {
    "hotels": [{
      "itemId": "32",
      "checkInDate": "2026-07-18",
      "checkOutDate": "2026-07-20",
      "leadTravelerIndex": 1,
      "paymentPolicy": "GUARANTEE",
      "room": { "travelerIndices": [1] },
      "numberOfGuests": 1
    }],
    "travelers": [
      { "givenName": "Josh", "surname": "Janzen", "passengerCode": "ADT" }
    ]
  },
  "retrieveBooking": true,
  "receivedFrom": "API"
}
```

With `retrieveBooking: true` the response returns the updated `booking`
(same Get Booking structure as §5, with the new `checkInDate`/`checkOutDate`).
No saved modify response existed in the collections; the shape is inferred
from the documented "response mirrors Get Booking" pattern verified for
create and cancel (medium-high confidence).
