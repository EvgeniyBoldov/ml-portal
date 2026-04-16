# MCP Credential Flow

## Purpose

This document describes how credentials move from platform ownership to MCP-backed execution.

## Core Rule

MCP servers should receive short-lived credentials, not permanent raw secrets.

## Flow

1. Runtime resolves an operation.
2. Runtime determines the required credential scope.
3. Platform issues a session-scoped secret payload or signed retrieval link.
4. MCP provider consumes the secret for the current session or call.

## Properties

- explicit expiry,
- short lifetime,
- revocation support,
- auditability.

## Security Boundary

Credential ownership stays in the platform.
Transport is just delivery.

## Why This Exists

This is the binding mechanism between tool execution and secure secret delivery.
