// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ProofPulse
 * @notice On-chain provenance registry. Only fingerprints (hashes) and
 *         pseudonymous actor IDs are stored. Documents, titles and personal
 *         data never touch the chain.
 *
 * Trust model: a registrar (the ProofPulse backend signer) submits
 * transactions on behalf of authenticated users. The chain records WHO
 * (as a salted hash of the user id), WHAT (SHA-256 fingerprint) and WHEN
 * (block timestamp). Anyone can read the registry without the backend.
 */
contract ProofPulse {
    // ───────────── Types ─────────────
    struct Version {
        bytes32 contentHash;   // SHA-256 of the file bytes
        bytes32 metadataHash;  // hash of canonical off-chain metadata JSON
        bytes32 actorId;       // pseudonymous id of the user who made this version
        uint64 timestamp;
        uint32 approvals;
        uint32 rejections;
    }

    struct Record {
        bytes32 ownerId;       // pseudonymous owner id
        uint64 createdAt;
        bool exists;
        bool revoked;
        uint32 versionCount;
    }

    // ───────────── Storage ─────────────
    address public admin;
    mapping(address => bool) public registrars;

    mapping(bytes32 => Record) private records;
    mapping(bytes32 => mapping(uint32 => Version)) private versions;
    // recordId => versionIndex => approverId => decision (0 none, 1 approve, 2 reject)
    mapping(bytes32 => mapping(uint32 => mapping(bytes32 => uint8))) private decisions;
    // first record that claimed a content hash (duplicate/priority evidence)
    mapping(bytes32 => bytes32) public firstRecordForHash;

    uint256 public totalRecords;
    uint256 public totalVersions;
    uint256 public totalApprovals;

    // ───────────── Events ─────────────
    event RecordRegistered(bytes32 indexed recordId, bytes32 indexed contentHash, bytes32 ownerId, uint64 timestamp);
    event VersionAdded(bytes32 indexed recordId, uint32 indexed versionIndex, bytes32 contentHash, bytes32 actorId, uint64 timestamp);
    event DecisionRecorded(bytes32 indexed recordId, uint32 indexed versionIndex, bytes32 approverId, bool approved, bytes32 commentHash, uint64 timestamp);
    event RecordRevoked(bytes32 indexed recordId, bytes32 actorId, bytes32 reasonHash, uint64 timestamp);
    event RegistrarSet(address indexed registrar, bool allowed);
    event AdminTransferred(address indexed previousAdmin, address indexed newAdmin);

    // ───────────── Errors ─────────────
    error NotAdmin();
    error NotRegistrar();
    error AlreadyExists();
    error UnknownRecord();
    error RecordIsRevoked();
    error UnknownVersion();
    error AlreadyDecided();
    error EmptyHash();

    // ───────────── Modifiers ─────────────
    modifier onlyAdmin() {
        if (msg.sender != admin) revert NotAdmin();
        _;
    }

    modifier onlyRegistrar() {
        if (!registrars[msg.sender]) revert NotRegistrar();
        _;
    }

    constructor() {
        admin = msg.sender;
        registrars[msg.sender] = true;
        emit AdminTransferred(address(0), msg.sender);
        emit RegistrarSet(msg.sender, true);
    }

    // ───────────── Admin ─────────────
    function setRegistrar(address registrar, bool allowed) external onlyAdmin {
        registrars[registrar] = allowed;
        emit RegistrarSet(registrar, allowed);
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        emit AdminTransferred(admin, newAdmin);
        admin = newAdmin;
    }

    // ───────────── Writes ─────────────
    function registerRecord(
        bytes32 recordId,
        bytes32 contentHash,
        bytes32 metadataHash,
        bytes32 ownerId
    ) external onlyRegistrar {
        if (contentHash == bytes32(0)) revert EmptyHash();
        if (records[recordId].exists) revert AlreadyExists();

        records[recordId] = Record({
            ownerId: ownerId,
            createdAt: uint64(block.timestamp),
            exists: true,
            revoked: false,
            versionCount: 1
        });
        versions[recordId][1] = Version(contentHash, metadataHash, ownerId, uint64(block.timestamp), 0, 0);

        if (firstRecordForHash[contentHash] == bytes32(0)) {
            firstRecordForHash[contentHash] = recordId;
        }
        totalRecords += 1;
        totalVersions += 1;

        emit RecordRegistered(recordId, contentHash, ownerId, uint64(block.timestamp));
        emit VersionAdded(recordId, 1, contentHash, ownerId, uint64(block.timestamp));
    }

    function addVersion(
        bytes32 recordId,
        bytes32 contentHash,
        bytes32 metadataHash,
        bytes32 actorId
    ) external onlyRegistrar returns (uint32 versionIndex) {
        if (contentHash == bytes32(0)) revert EmptyHash();
        Record storage r = records[recordId];
        if (!r.exists) revert UnknownRecord();
        if (r.revoked) revert RecordIsRevoked();

        r.versionCount += 1;
        versionIndex = r.versionCount;
        versions[recordId][versionIndex] = Version(contentHash, metadataHash, actorId, uint64(block.timestamp), 0, 0);

        if (firstRecordForHash[contentHash] == bytes32(0)) {
            firstRecordForHash[contentHash] = recordId;
        }
        totalVersions += 1;
        emit VersionAdded(recordId, versionIndex, contentHash, actorId, uint64(block.timestamp));
    }

    function recordDecision(
        bytes32 recordId,
        uint32 versionIndex,
        bytes32 approverId,
        bool approved,
        bytes32 commentHash
    ) external onlyRegistrar {
        Record storage r = records[recordId];
        if (!r.exists) revert UnknownRecord();
        if (r.revoked) revert RecordIsRevoked();
        if (versionIndex == 0 || versionIndex > r.versionCount) revert UnknownVersion();
        if (decisions[recordId][versionIndex][approverId] != 0) revert AlreadyDecided();

        Version storage v = versions[recordId][versionIndex];
        if (approved) {
            decisions[recordId][versionIndex][approverId] = 1;
            v.approvals += 1;
            totalApprovals += 1;
        } else {
            decisions[recordId][versionIndex][approverId] = 2;
            v.rejections += 1;
        }
        emit DecisionRecorded(recordId, versionIndex, approverId, approved, commentHash, uint64(block.timestamp));
    }

    function revokeRecord(bytes32 recordId, bytes32 actorId, bytes32 reasonHash) external onlyRegistrar {
        Record storage r = records[recordId];
        if (!r.exists) revert UnknownRecord();
        if (r.revoked) revert RecordIsRevoked();
        r.revoked = true;
        emit RecordRevoked(recordId, actorId, reasonHash, uint64(block.timestamp));
    }

    // ───────────── Reads ─────────────
    function getRecord(bytes32 recordId)
        external
        view
        returns (bytes32 ownerId, uint64 createdAt, bool revoked, uint32 versionCount)
    {
        Record storage r = records[recordId];
        if (!r.exists) revert UnknownRecord();
        return (r.ownerId, r.createdAt, r.revoked, r.versionCount);
    }

    function getVersion(bytes32 recordId, uint32 versionIndex)
        external
        view
        returns (
            bytes32 contentHash,
            bytes32 metadataHash,
            bytes32 actorId,
            uint64 timestamp,
            uint32 approvals,
            uint32 rejections
        )
    {
        if (!records[recordId].exists) revert UnknownRecord();
        if (versionIndex == 0 || versionIndex > records[recordId].versionCount) revert UnknownVersion();
        Version storage v = versions[recordId][versionIndex];
        return (v.contentHash, v.metadataHash, v.actorId, v.timestamp, v.approvals, v.rejections);
    }

    function decisionOf(bytes32 recordId, uint32 versionIndex, bytes32 approverId) external view returns (uint8) {
        return decisions[recordId][versionIndex][approverId];
    }

    /// @notice True if `contentHash` equals the latest non-revoked version of the record.
    function verifyLatest(bytes32 recordId, bytes32 contentHash) external view returns (bool) {
        Record storage r = records[recordId];
        if (!r.exists || r.revoked) return false;
        return versions[recordId][r.versionCount].contentHash == contentHash;
    }

    /// @notice True if `contentHash` matches ANY historical version of the record.
    function verifyAny(bytes32 recordId, bytes32 contentHash) external view returns (bool, uint32) {
        Record storage r = records[recordId];
        if (!r.exists) return (false, 0);
        for (uint32 i = r.versionCount; i >= 1; i--) {
            if (versions[recordId][i].contentHash == contentHash) return (true, i);
            if (i == 1) break;
        }
        return (false, 0);
    }
}
