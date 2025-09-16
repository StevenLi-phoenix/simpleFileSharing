#include "storage.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <fstream>
#include <random>
#include <regex>
#include <sstream>
#include <system_error>

using namespace std;

namespace fs = std::filesystem;

Storage::Storage(StorageConfig cfg) : cfg_(std::move(cfg)) {}

bool Storage::init() {
    if (!ensure_dirs()) return false;
    load_mapping();
    return true;
}

bool Storage::ensure_dirs() {
    error_code ec;
    if (!fs::exists(cfg_.resources_dir, ec)) {
        if (!fs::create_directories(cfg_.resources_dir, ec)) {
            return false;
        }
    }
    return true;
}

bool Storage::load_mapping() {
    ifstream in(cfg_.mapping_path);
    if (!in.good()) {
        return true; // start empty
    }
    stringstream buffer;
    buffer << in.rdbuf();
    auto obj = parse_json_object_string_map(buffer.str());
    unique_lock lock(mu_);
    mapping_ = std::move(obj);
    return true;
}

bool Storage::save_mapping(string* err) const {
    string tmp = cfg_.mapping_path.string() + ".tmp";
    string body;
    {
        shared_lock lock(mu_);
        body = to_json_object_string_map(mapping_);
    }
    ofstream out(tmp, ios::trunc);
    if (!out.good()) {
        if (err) *err = "Failed to open temp mapping for write";
        return false;
    }
    out << body;
    out.flush();
    out.close();
    error_code ec;
    fs::rename(tmp, cfg_.mapping_path, ec);
    if (ec) {
        if (err) *err = string("Rename failed: ") + ec.message();
        return false;
    }
    return true;
}

string Storage::generate_id(size_t len) {
    static const char* kAlphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
    random_device rd;
    mt19937_64 gen(rd());
    uniform_int_distribution<size_t> dist(0, 61);
    string s;
    s.reserve(len);
    for (size_t i = 0; i < len; ++i) s.push_back(kAlphabet[dist(gen)]);
    return s;
}

bool Storage::is_valid_id(const string& id) {
    static const regex re("^[A-Za-z0-9]{6,64}$");
    return regex_match(id, re);
}

vector<pair<string, string>> Storage::list() const {
    shared_lock lock(mu_);
    vector<pair<string, string>> v;
    v.reserve(mapping_.size());
    for (auto& [k, val] : mapping_) v.emplace_back(k, val);
    sort(v.begin(), v.end(), [](auto& a, auto& b) { return a.first < b.first; });
    return v;
}

bool Storage::get_original_name(const string& id, string& out) const {
    shared_lock lock(mu_);
    auto it = mapping_.find(id);
    if (it == mapping_.end()) return false;
    out = it->second;
    return true;
}

optional<fs::path> Storage::blob_path_for(const string& id) const {
    if (!is_valid_id(id)) return nullopt;
    fs::path p = cfg_.resources_dir / id;
    if (fs::exists(p)) return p;
    return nullopt;
}

bool Storage::add_file_from_path(const fs::path& src, string& out_id, string* out_orig_name, string* err) {
    error_code ec;
    if (!fs::exists(src, ec)) {
        if (err) *err = "Source file does not exist";
        return false;
    }
    auto fsize = fs::file_size(src, ec);
    if (ec) {
        if (err) *err = string("Failed to stat file: ") + ec.message();
        return false;
    }
    if (cfg_.max_file_size > 0 && static_cast<size_t>(fsize) > cfg_.max_file_size) {
        if (err) *err = "File exceeds size limit";
        return false;
    }
    string orig = src.filename().string();
    string id;
    // Ensure unique ID
    for (int attempt = 0; attempt < 10; ++attempt) {
        string candidate = generate_id();
        fs::path dest = cfg_.resources_dir / candidate;
        if (!fs::exists(dest)) { id = candidate; break; }
    }
    if (id.empty()) {
        if (err) *err = "Failed to generate unique ID";
        return false;
    }
    fs::path tmp = cfg_.resources_dir / (id + ".tmp");
    // Copy to tmp then rename
    fs::copy_file(src, tmp, fs::copy_options::overwrite_existing, ec);
    if (ec) {
        if (err) *err = string("Copy failed: ") + ec.message();
        return false;
    }
    fs::path finalp = cfg_.resources_dir / id;
    fs::rename(tmp, finalp, ec);
    if (ec) {
        if (err) *err = string("Rename failed: ") + ec.message();
        return false;
    }
    {
        unique_lock lock(mu_);
        mapping_[id] = sanitize_filename(orig);
    }
    string save_err;
    if (!save_mapping(&save_err)) {
        if (err) *err = string("Saved file, but failed to persist mapping: ") + save_err;
        // keep file; mapping will be rebuilt on next mutation
    }
    out_id = id;
    if (out_orig_name) *out_orig_name = orig;
    return true;
}

bool Storage::add_file_from_buffer(const string& buffer, const string& original_name, string& out_id, string* err) {
    if (cfg_.max_file_size > 0 && buffer.size() > cfg_.max_file_size) {
        if (err) *err = "File exceeds size limit";
        return false;
    }
    string id;
    for (int attempt = 0; attempt < 10; ++attempt) {
        string candidate = generate_id();
        fs::path dest = cfg_.resources_dir / candidate;
        if (!fs::exists(dest)) { id = candidate; break; }
    }
    if (id.empty()) {
        if (err) *err = "Failed to generate unique ID";
        return false;
    }
    fs::path tmp = cfg_.resources_dir / (id + ".tmp");
    {
        ofstream out(tmp, ios::binary | ios::trunc);
        if (!out.good()) {
            if (err) *err = "Failed to open temp file for write";
            return false;
        }
        out.write(buffer.data(), static_cast<streamsize>(buffer.size()));
        out.close();
    }
    error_code ec;
    fs::path finalp = cfg_.resources_dir / id;
    fs::rename(tmp, finalp, ec);
    if (ec) {
        if (err) *err = string("Rename failed: ") + ec.message();
        return false;
    }
    {
        unique_lock lock(mu_);
        mapping_[id] = sanitize_filename(original_name);
    }
    string save_err;
    if (!save_mapping(&save_err)) {
        if (err) *err = string("Saved file, but failed to persist mapping: ") + save_err;
    }
    out_id = id;
    return true;
}

bool Storage::delete_file(const string& id, string* err) {
    if (!is_valid_id(id)) { if (err) *err = "Invalid id"; return false; }
    error_code ec;
    fs::path p = cfg_.resources_dir / id;
    if (!fs::exists(p, ec)) { if (err) *err = "Not found"; return false; }
    fs::remove(p, ec);
    if (ec) { if (err) *err = string("Failed to remove file: ") + ec.message(); return false; }
    {
        unique_lock lock(mu_);
        mapping_.erase(id);
    }
    if (!save_mapping(err)) {
        return false;
    }
    return true;
}

string Storage::sanitize_filename(const string& name) {
    string out;
    out.reserve(name.size());
    for (unsigned char c : name) {
        if (c == '"' || c == '\\' || c < 0x20) out.push_back('_');
        else out.push_back(static_cast<char>(c));
    }
    return out;
}

// Minimal JSON parse for {"k":"v", ...}
unordered_map<string, string> Storage::parse_json_object_string_map(const string& content) {
    unordered_map<string, string> m;
    size_t i = 0, n = content.size();
    auto skip_ws = [&](void){ while (i < n && isspace(static_cast<unsigned char>(content[i]))) ++i; };
    auto parse_string = [&](string& out)->bool {
        if (i >= n || content[i] != '"') return false;
        ++i; // skip quote
        out.clear();
        while (i < n) {
            char c = content[i++];
            if (c == '"') return true;
            if (c == '\\' && i < n) {
                char e = content[i++];
                if (e == '"' || e == '\\' || e == '/') out.push_back(e);
                else if (e == 'b') out.push_back('\b');
                else if (e == 'f') out.push_back('\f');
                else if (e == 'n') out.push_back('\n');
                else if (e == 'r') out.push_back('\r');
                else if (e == 't') out.push_back('\t');
                else { /* ignore other escapes (uXXXX not supported) */ }
            } else {
                out.push_back(c);
            }
        }
        return false;
    };
    skip_ws();
    if (i >= n || content[i] != '{') return m;
    ++i;
    skip_ws();
    if (i < n && content[i] == '}') return m; // empty
    while (i < n) {
        skip_ws();
        string key, val;
        if (!parse_string(key)) break;
        skip_ws();
        if (i >= n || content[i] != ':') break;
        ++i; // colon
        skip_ws();
        if (!parse_string(val)) break;
        m[key] = val;
        skip_ws();
        if (i < n && content[i] == ',') { ++i; continue; }
        if (i < n && content[i] == '}') { ++i; break; }
    }
    return m;
}

static string json_escape(const string& s) {
    string out;
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) out += '_'; else out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

string Storage::to_json_object_string_map(const unordered_map<string, string>& m) {
    string out = "{";
    bool first = true;
    for (auto& kv : m) {
        if (!first) out += ",";
        first = false;
        out += '"'; out += json_escape(kv.first); out += '"';
        out += ":";
        out += '"'; out += json_escape(kv.second); out += '"';
    }
    out += "}";
    return out;
}
