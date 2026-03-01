#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../include/decoder.h"
#include "../include/ini_parser.h"
#include "../include/ms2d.h"
#include "../include/project_parser.h"
#include "../include/rpc_server.h"
#include "../include/serial_comm.h"

/* Default configuration values */
#define MS2D_DEFAULT_SOCKET_PATH "/tmp/ms2d.sock"
#define MS2D_DEFAULT_POLL_RATE_HZ 10
#define MS2D_POLL_INTERVAL_MS (1000 / MS2D_DEFAULT_POLL_RATE_HZ)
#define MS2D_MAIN_LOOP_SLEEP_MS 10
#define MS2D_BACKOFF_INITIAL_MS 1000
#define MS2D_BACKOFF_MAX_MS 30000

/* Global state for signal handler */
static volatile sig_atomic_t g_running = 1;

/* Signal handler for SIGTERM and SIGINT */
static void signal_handler(int signum)
{
    (void)signum;
    g_running = 0;
}

/* Print usage information */
static void print_usage(const char *progname)
{
    fprintf(stderr, "Usage: %s [OPTIONS]\n", progname);
    fprintf(stderr, "\n");
    fprintf(stderr, "MS2D - Megasquirt 2 Daemon\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "Options:\n");
    fprintf(stderr, "  -p, --port <path>      Serial port path (e.g., /dev/ttyUSB0 or /tmp/ms2_ecu_sim)\n");
    fprintf(stderr, "  -i, --ini <path>       INI file path\n");
    fprintf(stderr, "  -s, --socket <path>    Unix socket path (default: %s)\n", MS2D_DEFAULT_SOCKET_PATH);
    fprintf(stderr, "  -P, --project <dir>    TunerStudio project directory (auto-configures)\n");
    fprintf(stderr, "  -v, --verbose          Enable verbose logging\n");
    fprintf(stderr, "  -h, --help             Print this help message\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "Examples:\n");
    fprintf(stderr, "  %s --port /dev/ttyUSB0 --ini cfg.ini\n", progname);
    fprintf(stderr, "  %s --port /tmp/ms2_ecu_sim --ini cfg.ini --socket /tmp/ms2d.sock\n", progname);
    fprintf(stderr, "  %s --project ./projectCfg/\n", progname);
    fprintf(stderr, "\n");
}

/* Worker thread function: polls ECU at 10Hz */
static void *worker_thread(void *arg)
{
    ms2d_state_t *state = (ms2d_state_t *)arg;
    uint32_t backoff_ms = 0;
    int consecutive_failures = 0;

    while (g_running) {
        /* Poll ECU for OUTPC data */
        ms2d_error_t err = ms2d_serial_poll_outpc(state);
        
        if (err == MS2D_SUCCESS) {
            /* Update last poll timestamp - reset backoff on success */
            (void)ms2d_timestamp_ms();  /* Could store in state if needed */
            pthread_mutex_lock(&state->mutex);
            pthread_mutex_unlock(&state->mutex);
            
            /* Reset backoff on success */
            backoff_ms = 0;
            consecutive_failures = 0;
            
            /* Sleep to maintain 10Hz rate (100ms) */
            usleep(MS2D_POLL_INTERVAL_MS * 1000);
        } else {
            /* Serial error - apply exponential backoff */
            consecutive_failures++;
            
            if (backoff_ms == 0) {
                backoff_ms = MS2D_BACKOFF_INITIAL_MS;
            } else {
                backoff_ms *= 2;
                if (backoff_ms > MS2D_BACKOFF_MAX_MS) {
                    backoff_ms = MS2D_BACKOFF_MAX_MS;
                }
            }
            
            fprintf(stderr, "Serial poll failed (attempt %d): %s, retrying in %u ms\n",
                    consecutive_failures, ms2d_error_str(err), backoff_ms);
            
            /* Close and reopen serial connection */
            if (state->serial_fd >= 0) {
                ms2d_serial_close(state);
            }
            
            /* Sleep for backoff period */
            usleep(backoff_ms * 1000);
            
            /* Attempt to reconnect */
            if (g_running) {
                ms2d_error_t reconnect_err = ms2d_serial_open(state);
                if (reconnect_err == MS2D_SUCCESS) {
                    fprintf(stderr, "Serial reconnection successful\n");
                    backoff_ms = 0;
                    consecutive_failures = 0;
                } else {
                    fprintf(stderr, "Serial reconnection failed: %s\n", ms2d_error_str(reconnect_err));
                }
            }
        }
    }
    
    return NULL;
}

/* Main function */
int main(int argc, char *argv[])
{
    /* Command-line options */
    const char *port = NULL;
    const char *ini_file = NULL;
    const char *socket_path = MS2D_DEFAULT_SOCKET_PATH;
    const char *project_dir = NULL;
    int verbose = 0;
    
    /* Parse command-line arguments */
    static struct option long_options[] = {
        {"port",    required_argument, 0, 'p'},
        {"ini",     required_argument, 0, 'i'},
        {"socket",  required_argument, 0, 's'},
        {"project", required_argument, 0, 'P'},
        {"verbose", no_argument,       0, 'v'},
        {"help",    no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };
    
    int opt;
    int option_index = 0;
    
    while ((opt = getopt_long(argc, argv, "p:i:s:P:vh", long_options, &option_index)) != -1) {
        switch (opt) {
            case 'p':
                port = optarg;
                break;
            case 'i':
                ini_file = optarg;
                break;
            case 's':
                socket_path = optarg;
                break;
            case 'P':
                project_dir = optarg;
                break;
            case 'v':
                verbose = 1;
                break;
            case 'h':
                print_usage(argv[0]);
                return 0;
            default:
                print_usage(argv[0]);
                return 1;
        }
    }
    
    /* Initialize state */
    ms2d_state_t state;
    memset(&state, 0, sizeof(state));
    state.serial_fd = -1;
    state.running = 1;
    
    /* Initialize mutex */
    if (pthread_mutex_init(&state.mutex, NULL) != 0) {
        fprintf(stderr, "Error: Failed to initialize mutex\n");
        return 1;
    }
    
    /* Load configuration */
    if (project_dir) {
        /* Project mode: auto-load configuration from TunerStudio project */
        if (verbose) {
            fprintf(stderr, "Loading configuration from project directory: %s\n", project_dir);
        }
        
        ms2d_error_t err = ms2d_project_parse(project_dir, &state.config);
        if (err != MS2D_SUCCESS) {
            fprintf(stderr, "Error: Failed to parse project directory: %s\n", ms2d_error_str(err));
            pthread_mutex_destroy(&state.mutex);
            return 1;
        }
        
        if (verbose) {
            fprintf(stderr, "  Serial port: %s\n", state.config.serial_port);
            fprintf(stderr, "  Baud rate: %u\n", state.config.baud_rate);
            fprintf(stderr, "  INI file: %s\n", state.config.ini_file);
        }
    } else {
        /* Manual mode: require --port and --ini */
        if (!port || !ini_file) {
            fprintf(stderr, "Error: Either --project or both --port and --ini are required\n");
            print_usage(argv[0]);
            pthread_mutex_destroy(&state.mutex);
            return 1;
        }
        
        /* Copy configuration */
        strncpy(state.config.serial_port, port, sizeof(state.config.serial_port) - 1);
        state.config.serial_port[sizeof(state.config.serial_port) - 1] = '\0';
        
        strncpy(state.config.ini_file, ini_file, sizeof(state.config.ini_file) - 1);
        state.config.ini_file[sizeof(state.config.ini_file) - 1] = '\0';
        
        state.config.baud_rate = 115200; /* Default baud rate */
    }
    
    /* Parse INI file */
    if (verbose) {
        fprintf(stderr, "Parsing INI file: %s\n", state.config.ini_file);
    }
    
    ms2d_error_t err = ms2d_ini_parse(state.config.ini_file, &state.fields, &state.num_fields);
    if (err != MS2D_SUCCESS) {
        fprintf(stderr, "Error: Failed to parse INI file: %s\n", ms2d_error_str(err));
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }
    
    if (verbose) {
        fprintf(stderr, "  Parsed %u fields\n", state.num_fields);
    }
    
    /* Open serial port */
    if (verbose) {
        fprintf(stderr, "Opening serial port: %s\n", state.config.serial_port);
    }
    
    err = ms2d_serial_open(&state);
    if (err != MS2D_SUCCESS) {
        fprintf(stderr, "Error: Failed to open serial port: %s\n", ms2d_error_str(err));
        free(state.fields);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }
    
    if (verbose) {
        fprintf(stderr, "Serial port opened successfully (fd=%d)\n", state.serial_fd);
    }
    
    /* Set socket path in environment for RPC server */
    setenv("MS2D_RPC_SOCKET_PATH", socket_path, 1);
    
    /* Initialize RPC server */
    if (verbose) {
        fprintf(stderr, "Initializing RPC server: %s\n", socket_path);
    }
    
    err = ms2d_rpc_init(&state);
    if (err != MS2D_SUCCESS) {
        fprintf(stderr, "Error: Failed to initialize RPC server: %s\n", ms2d_error_str(err));
        ms2d_serial_close(&state);
        free(state.fields);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }
    
    if (verbose) {
        fprintf(stderr, "RPC server initialized successfully\n");
    }
    
    /* Register signal handlers */
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    
    if (sigaction(SIGTERM, &sa, NULL) < 0 || sigaction(SIGINT, &sa, NULL) < 0) {
        fprintf(stderr, "Error: Failed to register signal handlers\n");
        ms2d_rpc_shutdown(&state);
        ms2d_serial_close(&state);
        free(state.fields);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }
    
    if (verbose) {
        fprintf(stderr, "Signal handlers registered\n");
    }
    
    /* Create worker thread for serial polling */
    pthread_t worker_tid;
    if (pthread_create(&worker_tid, NULL, worker_thread, &state) != 0) {
        fprintf(stderr, "Error: Failed to create worker thread\n");
        ms2d_rpc_shutdown(&state);
        ms2d_serial_close(&state);
        free(state.fields);
        pthread_mutex_destroy(&state.mutex);
        return 1;
    }
    
    if (verbose) {
        fprintf(stderr, "Worker thread created\n");
        fprintf(stderr, "Daemon started successfully\n");
        fprintf(stderr, "Press Ctrl+C to exit\n");
    }
    
    /* Main loop: handle RPC requests */
    while (g_running) {
        /* Accept new RPC clients (non-blocking) */
        ms2d_error_t accept_err = ms2d_rpc_accept(&state);
        if (accept_err != MS2D_SUCCESS && accept_err != MS2D_ERROR_TIMEOUT) {
            /* Log error but continue */
            if (verbose) {
                fprintf(stderr, "RPC accept error: %s\n", ms2d_error_str(accept_err));
            }
        }
        
        /* Sleep briefly to avoid busy-waiting */
        usleep(MS2D_MAIN_LOOP_SLEEP_MS * 1000);
    }
    
    /* Cleanup */
    if (verbose) {
        fprintf(stderr, "\nShutting down...\n");
    }
    
    /* Join worker thread */
    pthread_join(worker_tid, NULL);
    
    if (verbose) {
        fprintf(stderr, "Worker thread joined\n");
    }
    
    /* Shutdown RPC server */
    ms2d_rpc_shutdown(&state);
    
    if (verbose) {
        fprintf(stderr, "RPC server shutdown\n");
    }
    
    /* Close serial port */
    if (state.serial_fd >= 0) {
        ms2d_serial_close(&state);
    }
    
    if (verbose) {
        fprintf(stderr, "Serial port closed\n");
    }
    
    /* Free allocated memory */
    if (state.fields) {
        free(state.fields);
    }
    
    if (state.outpc_buffer) {
        free(state.outpc_buffer);
    }
    
    if (state.config.custom_fields) {
        free(state.config.custom_fields);
    }
    
    /* Destroy mutex */
    pthread_mutex_destroy(&state.mutex);
    
    if (verbose) {
        fprintf(stderr, "Cleanup complete\n");
    }
    
    return 0;
}
