#include "ms2_client.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    const char *socket_path = "/tmp/ms2d.sock";

    /* Allow override via command line */
    if (argc > 1) {
        socket_path = argv[1];
    }

    printf("MS2D C Client Example\n");
    printf("Connecting to daemon at: %s\n\n", socket_path);

    /* Connect to daemon */
    ms2_client_t *client = ms2_connect(socket_path);
    if (!client) {
        fprintf(stderr, "ERROR: Failed to connect to daemon\n");
        return 1;
    }
    printf("Connected successfully.\n\n");

    /* Get daemon status */
    int connected = 0;
    char signature[256] = {0};
    if (ms2_get_status(client, &connected, signature, sizeof(signature)) == 0) {
        printf("Daemon Status:\n");
        printf("  Connected to ECU: %s\n", connected ? "yes" : "no");
        printf("  ECU Signature: %s\n\n", signature);
    } else {
        fprintf(stderr, "ERROR: Failed to get daemon status\n");
    }

    /* Get single field value (RPM) */
    printf("Querying single field: rpm\n");
    double rpm = ms2_get_value(client, "rpm");
    printf("  rpm: %.1f\n\n", rpm);

    /* Get multiple field values */
    printf("Querying multiple fields: rpm, batteryVoltage, coolant\n");
    const char *fields[] = {"rpm", "batteryVoltage", "coolant"};
    double values[3] = {0};
    if (ms2_get_values(client, fields, 3, values) == 0) {
        printf("  rpm: %.1f\n", values[0]);
        printf("  batteryVoltage: %.2f V\n", values[1]);
        printf("  coolant: %.1f\n\n", values[2]);
    } else {
        fprintf(stderr, "ERROR: Failed to get multiple values\n");
    }

    /* List all available fields */
    printf("Listing all available fields:\n");
    int field_count = 0;
    char **field_names = ms2_list_fields(client, &field_count);
    if (field_names) {
        printf("  Total fields: %d\n", field_count);
        printf("  First 10 fields:\n");
        for (int i = 0; i < field_count && i < 10; i++) {
            printf("    %d. %s\n", i + 1, field_names[i]);
        }
        ms2_free_fields(field_names, field_count);
    } else {
        fprintf(stderr, "ERROR: Failed to list fields\n");
    }

    /* Disconnect */
    printf("\nDisconnecting...\n");
    ms2_disconnect(client);
    printf("Done.\n");

    return 0;
}
