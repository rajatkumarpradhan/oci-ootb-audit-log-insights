# Deploy: archive OCI Audit logs to Object Storage, then analyze them offline

**Status: prepared, not deployed. These steps have not been executed on a live
tenancy, and the configs carry `<...>` placeholders to fill at deploy time.
Nothing here creates resources by itself.**

The pipeline uses only built-in OCI services: the Audit service (always on in
every tenancy) records API calls, Connector Hub moves them into an Object
Storage bucket, and this repo's analyzer reads the archived files offline.

Cost (Oracle-published pages, checked 28 Oct 2026):
[Connector Hub is free](https://www.oracle.com/application-development/connector-hub/pricing/)
("no charge for using Connector Hub"; standard rates apply for the source and
target services), and
[Object Storage has a 20 GB Always Free tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).
Audit log retention in the Audit service is
[365 days](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm).
Limits and billing are Oracle's to change; the links are the source of truth.

## 1. Create the archive bucket

Console: Storage -> Object Storage -> Create Bucket, name `audit-archive`,
default settings (private).

CLI:
```
oci os bucket create --name audit-archive --compartment-id <compartment-ocid>
```

## 2. Find the Audit log group OCID

Console: Observability -> Logging -> Log Groups -> `_Audit`. Copy its OCID
into `config/service-connector.json` as `source.logGroupId`.

CLI: `oci logging log-group list --compartment-id <compartment-ocid>`

## 3. Create the connector

Fill `<compartment-ocid>` in both config files, then:

```
oci sch service-connector create --from-json file://config/service-connector.json
```

Console equivalent: Observability -> Connector Hub -> Create Connector ->
source: Logging, log group `_Audit`; target: Object Storage, bucket
`audit-archive`. Keep the default batching (100 MB / 420 s in the config).

## 4. Verify

Make some API calls (list buckets, open the Console), wait one batch interval
(~7 minutes), then check the bucket for new objects:

```
oci os object list --bucket-name audit-archive
```

## 5. Analyze

Download a batch and run the analyzer on it:

```
oci os object bulk-download --bucket-name audit-archive --download-dir ./archive
python3 -m analyzer ./archive
```

The analyzer reads `.jsonl`, `.json` and `.gz` files, skips malformed lines
with a count, and prints principals, source IPs, operations, response
statuses, 4xx denials, write operations and a per-day timeline. It makes no
API calls.

## 6. Clean up

```
oci sch service-connector delete --service-connector-id <connector-ocid> --force
oci os object bulk-delete --bucket-name audit-archive
oci os bucket delete --bucket-name audit-archive --empty
```

## Optional next steps

- Target a Notifications topic instead (alert on denials) - that pipeline
  shape is covered by the sibling repo `oci-ootb-upload-alerts`.
- Schedule the analyzer on an Always Free VM against freshly downloaded
  batches.
