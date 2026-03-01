#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

int main() {
    int sockfd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sockfd < 0) {
        perror("socket");
        return 1;
    }
    printf("Socket created: %d\n", sockfd);

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, "/tmp/ms2d.sock", sizeof(addr.sun_path) - 1);

    printf("Connecting...\n");
    if (connect(sockfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("connect");
        close(sockfd);
        return 1;
    }
    printf("Connected successfully\n");

    const char *request = "{\"jsonrpc\":\"2.0\",\"method\":\"get_status\",\"id\":1}";
    printf("Sending: %s\n", request);
    ssize_t sent = send(sockfd, request, strlen(request), 0);
    printf("Sent %zd bytes\n", sent);

    char buffer[4096];
    printf("Receiving...\n");
    ssize_t received = recv(sockfd, buffer, sizeof(buffer) - 1, 0);
    printf("Received %zd bytes\n", received);
    if (received > 0) {
        buffer[received] = '\0';
        printf("Response:\n%s\n", buffer);
    }

    close(sockfd);
    return 0;
}
