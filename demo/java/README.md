# CODI Demo — Spring Boot (Java)

This directory hosts a lightweight Spring Boot application. The accompanying Dockerfile is
deliberately naive: it runs with the full Maven toolchain inside the container, providing ample
opportunities for CODI to optimise build time and image size.

## Local Development

```bash
mvn spring-boot:run
```

## Container Build (naive)

```bash
docker build -t codi-demo-java .
docker run --rm -p 8080:8080 codi-demo-java
```
