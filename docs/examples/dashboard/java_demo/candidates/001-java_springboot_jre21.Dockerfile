# RATIONALE: Split build and runtime; use Temurin JRE; non-root runtime.
# POLICY: Pinned base tags; skip tests for speed; non-root user.
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /workspace
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2 mvn -B -e -ntp -q -DskipTests dependency:go-offline
COPY . .
RUN --mount=type=cache,target=/root/.m2 mvn -B -e -ntp -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
# Create non-root user
RUN useradd -u 10001 -m codi
USER 10001
COPY --from=builder /workspace/target/*.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
