#pragma once

#include <filesystem>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <unordered_map>
#include <vector>
#include <optional>

struct StorageConfig {
    std::filesystem::path resources_dir{"resources"};
    std::filesystem::path mapping_path{"mapping.json"};
    std::size_t max_file_size{0}; // 0 = no limit by default
};

class Storage {
public:
    explicit Storage(StorageConfig cfg);

    bool init();

    // ID management
    static std::string generate_id(std::size_t len = 22);
    static bool is_valid_id(const std::string& id);

    // Listing
    std::vector<std::pair<std::string, std::string>> list() const;

    // Lookups
    bool get_original_name(const std::string& id, std::string& out) const;
    std::optional<std::filesystem::path> blob_path_for(const std::string& id) const;

    // Mutations
    bool add_file_from_path(const std::filesystem::path& src, std::string& out_id, std::string* out_orig_name = nullptr, std::string* err = nullptr);
    bool add_file_from_buffer(const std::string& buffer, const std::string& original_name, std::string& out_id, std::string* err = nullptr);
    bool delete_file(const std::string& id, std::string* err = nullptr);

    // Config access
    const StorageConfig& config() const { return cfg_; }

private:
    bool ensure_dirs();
    bool load_mapping();
    bool save_mapping(std::string* err = nullptr) const;
    static std::string sanitize_filename(const std::string& name);

    // Minimal JSON helpers
    static std::unordered_map<std::string, std::string> parse_json_object_string_map(const std::string& content);
    static std::string to_json_object_string_map(const std::unordered_map<std::string, std::string>& m);

    StorageConfig cfg_;
    mutable std::shared_mutex mu_;
    std::unordered_map<std::string, std::string> mapping_;
};
