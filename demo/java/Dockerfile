# Naive Dockerfile for the CODI Spring Boot demo application.
FROM maven:3.9.6-eclipse-temurin-21

WORKDIR /workspace
COPY pom.xml ./
COPY src src

EXPOSE 8080
CMD ["mvn", "spring-boot:run"]
