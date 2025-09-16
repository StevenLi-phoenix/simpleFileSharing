#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <algorithm>

#include "storage.h"
#include "html.hpp"

#if __has_include("httplib.h")
#  include "httplib.h"
#  define HAVE_HTTPLIB 1
#else
#  define HAVE_HTTPLIB 0
#endif

using namespace std;

static size_t env_to_sizet(const char* name, size_t def) {
    const char* v = std::getenv(name);
    if (!v) return def;
    try {
        return static_cast<size_t>(stoull(string(v)));
    } catch (...) { return def; }
}

#if HAVE_HTTPLIB
static bool parse_multipart_file(const std::string& body, const std::string& content_type,
                                 std::string& out_filename, std::string& out_content) {
    // Expect: Content-Type: multipart/form-data; boundary=XYZ
    auto ct = content_type;
    auto pos = ct.find("boundary=");
    if (pos == std::string::npos) return false;
    std::string boundary = ct.substr(pos + 9);
    if (!boundary.empty() && boundary.front() == '"' && boundary.back() == '"') {
        boundary = boundary.substr(1, boundary.size() - 2);
    }
    std::string sep = "--" + boundary;
    std::string end = sep + "--";

    // Split by boundary markers
    size_t start = 0;
    while (true) {
        size_t p = body.find(sep, start);
        if (p == std::string::npos) break;
        p += sep.size();
        // Expect CRLF
        if (p + 2 > body.size() || body[p] != '\r' || body[p+1] != '\n') { start = p; continue; }
        p += 2;
        // Read headers until CRLFCRLF
        size_t hdr_end = body.find("\r\n\r\n", p);
        if (hdr_end == std::string::npos) break;
        std::string headers = body.substr(p, hdr_end - p);
        // Move to content start
        size_t data_start = hdr_end + 4;
        // Find next boundary
        size_t next = body.find("\r\n" + sep, data_start);
        if (next == std::string::npos) next = body.find("\r\n" + end, data_start);
        if (next == std::string::npos) break;
        size_t data_end = next; // exclude trailing CRLF before boundary
        if (data_end >= 2 && body[data_end-2] == '\r' && body[data_end-1] == '\n') data_end -= 2;

        // Check Content-Disposition header
        std::string disp;
        {
            auto hpos = headers.find("Content-Disposition:");
            if (hpos != std::string::npos) {
                size_t line_end = headers.find("\r\n", hpos);
                disp = headers.substr(hpos, (line_end == std::string::npos ? headers.size() : line_end) - hpos);
            }
        }
        auto has_name_file = disp.find("name=\"file\"") != std::string::npos;
        if (has_name_file) {
            // Extract filename if present
            out_filename.clear();
            auto fnp = disp.find("filename=");
            if (fnp != std::string::npos) {
                size_t q1 = disp.find('"', fnp);
                size_t q2 = (q1 == std::string::npos ? std::string::npos : disp.find('"', q1+1));
                if (q1 != std::string::npos && q2 != std::string::npos && q2 > q1) {
                    out_filename = disp.substr(q1+1, q2 - (q1+1));
                }
            }
            out_content.assign(body.data() + data_start, body.data() + data_end);
            return true;
        }
        start = next + 2; // skip CRLF before boundary
    }
    return false;
}

static std::string get_header_ci(const httplib::Request& req, const std::string& key) {
    for (const auto& kv : req.headers) {
        if (kv.first.size() == key.size()) {
            bool eq = true;
            for (size_t i = 0; i < key.size(); ++i) {
                if (std::tolower(static_cast<unsigned char>(kv.first[i])) != std::tolower(static_cast<unsigned char>(key[i]))) { eq = false; break; }
            }
            if (eq) return kv.second;
        }
    }
    return {};
}
#endif

static std::string basename_only(std::string name) {
    auto p1 = name.find_last_of('/') ;
    auto p2 = name.find_last_of('\\');
    size_t pos = std::string::npos;
    if (p1 != std::string::npos && p2 != std::string::npos) pos = std::max(p1, p2);
    else pos = (p1 != std::string::npos ? p1 : p2);
    if (pos != std::string::npos) return name.substr(pos + 1);
    return name;
}

int main() {
    // Config from env vars; defaults align with Python app
    StorageConfig cfg;
    if (const char* p = std::getenv("RESOURCES_DIR")) cfg.resources_dir = p;
    if (const char* p = std::getenv("MAPPING_PATH")) cfg.mapping_path = p;
    cfg.max_file_size = env_to_sizet("MAX_FILE_SIZE", cfg.max_file_size);

    Storage storage(cfg);
    if (!storage.init()) {
        cerr << "Failed to initialize storage" << endl;
        return 1;
    }

#if HAVE_HTTPLIB
    httplib::Server svr;

    svr.Get("/", [&](const httplib::Request&, httplib::Response& res) {
        auto entries = storage.list();
        string html = render_index_html(entries, storage.config().max_file_size);
        res.set_content(html, "text/html; charset=utf-8");
    });

    svr.Post("/upload", [&](const httplib::Request& req, httplib::Response& res) {
        std::string filename;
        std::string content;
        // Try multipart first
        bool ok = false;
        std::string ct = get_header_ci(req, "Content-Type");
        if (!ct.empty() && ct.find("multipart/form-data") != std::string::npos) {
            ok = parse_multipart_file(req.body, ct, filename, content);
        }
        // Fallback: raw body
        if (!ok) {
            if (req.has_param("filename")) filename = req.get_param_value("filename");
            if (filename.empty()) {
                filename = "upload.bin"; // default when unspecified
            }
            content = req.body;
        }
        // Normalize filename to base name only
        filename = basename_only(filename);
        string id, err;
        if (!storage.add_file_from_buffer(content, filename, id, &err)) {
            res.status = 400;
            res.set_content(string("{\"error\":\"") + err + "\"}", "application/json");
            return;
        }
        // If browser form submit, redirect back to index; else return JSON
        std::string accept = get_header_ci(req, "Accept");
        if (!ct.empty() && ct.find("multipart/form-data") != std::string::npos && accept.find("text/html") != std::string::npos) {
            res.status = 303;
            res.set_header("Location", "/");
            return;
        }
        string body = string("{\"id\":\"") + id + "\",\"filename\":\"" + filename + "\"}";
        res.set_content(body, "application/json");
    });

    svr.Get(R"(/download/(.+))", [&](const httplib::Request& req, httplib::Response& res) {
        string id = req.matches[1];
        string name;
        if (!Storage::is_valid_id(id) || !storage.get_original_name(id, name)) {
            res.status = 404;
            res.set_content("{\"error\":\"Not found\"}", "application/json");
            return;
        }
        auto path = storage.blob_path_for(id);
        if (!path) { res.status = 404; res.set_content("{\"error\":\"Not found\"}", "application/json"); return; }
        // Read into memory (simple implementation)
        ifstream in(*path, ios::binary);
        std::string buf((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        res.set_header("Content-Disposition", string("attachment; filename=\"") + name + "\"");
        res.set_content(std::move(buf), "application/octet-stream");
    });

    svr.Delete(R"(/delete/(.+))", [&](const httplib::Request& req, httplib::Response& res) {
        string id = req.matches[1];
        string err;
        if (!storage.delete_file(id, &err)) {
            res.status = 404;
            if (err.empty()) err = "Not found";
            res.set_content(string("{\"error\":\"") + err + "\"}", "application/json");
            return;
        }
        res.set_content("{\"status\":\"ok\"}", "application/json");
    });

    int port = static_cast<int>(env_to_sizet("PORT", 8000));
    cout << "Server listening on http://127.0.0.1:" << port << endl;
    svr.listen("0.0.0.0", port);
#else
    cout << "Server built without HTTP library.\n"
            "To enable endpoints: place cpp-httplib's header at third_party/httplib.h\n"
            "Repo: https://github.com/yhirose/cpp-httplib (single-header).\n"
            "Then run: make server && ./bin/server\n";
#endif
    return 0;
}
