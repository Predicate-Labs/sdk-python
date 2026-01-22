export function analyze_page(val) {
    return takeObject(wasm.analyze_page(addHeapObject(val)));
}

export function analyze_page_with_options(val, options) {
    return takeObject(wasm.analyze_page_with_options(addHeapObject(val), addHeapObject(options)));
}

export function decide_and_act(_raw_elements) {
    wasm.decide_and_act(addHeapObject(_raw_elements));
}

export function prune_for_api(val) {
    return takeObject(wasm.prune_for_api(addHeapObject(val)));
}

function __wbg_get_imports() {
    const import0 = {
        __proto__: null,
        __wbg_Error_8c4e43fe74559d73: function(arg0, arg1) {
            return addHeapObject(Error(getStringFromWasm0(arg0, arg1)));
        },
        __wbg_Number_04624de7d0e8332d: function(arg0) {
            return Number(getObject(arg0));
        },
        __wbg___wbindgen_bigint_get_as_i64_8fcf4ce7f1ca72a2: function(arg0, arg1) {
            const v = getObject(arg1), ret = "bigint" == typeof v ? v : void 0;
            getDataViewMemory0().setBigInt64(arg0 + 8, isLikeNone(ret) ? BigInt(0) : ret, !0),
            getDataViewMemory0().setInt32(arg0 + 0, !isLikeNone(ret), !0);
        },
        __wbg___wbindgen_boolean_get_bbbb1c18aa2f5e25: function(arg0) {
            const v = getObject(arg0), ret = "boolean" == typeof v ? v : void 0;
            return isLikeNone(ret) ? 16777215 : ret ? 1 : 0;
        },
        __wbg___wbindgen_debug_string_0bc8482c6e3508ae: function(arg0, arg1) {
            const ptr1 = passStringToWasm0(debugString(getObject(arg1)), wasm.__wbindgen_export, wasm.__wbindgen_export2), len1 = WASM_VECTOR_LEN;
            getDataViewMemory0().setInt32(arg0 + 4, len1, !0), getDataViewMemory0().setInt32(arg0 + 0, ptr1, !0);
        },
        __wbg___wbindgen_in_47fa6863be6f2f25: function(arg0, arg1) {
            return getObject(arg0) in getObject(arg1);
        },
        __wbg___wbindgen_is_bigint_31b12575b56f32fc: function(arg0) {
            return "bigint" == typeof getObject(arg0);
        },
        __wbg___wbindgen_is_function_0095a73b8b156f76: function(arg0) {
            return "function" == typeof getObject(arg0);
        },
        __wbg___wbindgen_is_object_5ae8e5880f2c1fbd: function(arg0) {
            const val = getObject(arg0);
            return "object" == typeof val && null !== val;
        },
        __wbg___wbindgen_is_undefined_9e4d92534c42d778: function(arg0) {
            return void 0 === getObject(arg0);
        },
        __wbg___wbindgen_jsval_eq_11888390b0186270: function(arg0, arg1) {
            return getObject(arg0) === getObject(arg1);
        },
        __wbg___wbindgen_jsval_loose_eq_9dd77d8cd6671811: function(arg0, arg1) {
            return getObject(arg0) == getObject(arg1);
        },
        __wbg___wbindgen_number_get_8ff4255516ccad3e: function(arg0, arg1) {
            const obj = getObject(arg1), ret = "number" == typeof obj ? obj : void 0;
            getDataViewMemory0().setFloat64(arg0 + 8, isLikeNone(ret) ? 0 : ret, !0), getDataViewMemory0().setInt32(arg0 + 0, !isLikeNone(ret), !0);
        },
        __wbg___wbindgen_string_get_72fb696202c56729: function(arg0, arg1) {
            const obj = getObject(arg1), ret = "string" == typeof obj ? obj : void 0;
            var ptr1 = isLikeNone(ret) ? 0 : passStringToWasm0(ret, wasm.__wbindgen_export, wasm.__wbindgen_export2), len1 = WASM_VECTOR_LEN;
            getDataViewMemory0().setInt32(arg0 + 4, len1, !0), getDataViewMemory0().setInt32(arg0 + 0, ptr1, !0);
        },
        __wbg___wbindgen_throw_be289d5034ed271b: function(arg0, arg1) {
            throw new Error(getStringFromWasm0(arg0, arg1));
        },
        __wbg_call_389efe28435a9388: function() {
            return handleError(function(arg0, arg1) {
                return addHeapObject(getObject(arg0).call(getObject(arg1)));
            }, arguments);
        },
        __wbg_done_57b39ecd9addfe81: function(arg0) {
            return getObject(arg0).done;
        },
        __wbg_error_9a7fe3f932034cde: function(arg0) {},
        __wbg_get_9b94d73e6221f75c: function(arg0, arg1) {
            return addHeapObject(getObject(arg0)[arg1 >>> 0]);
        },
        __wbg_get_b3ed3ad4be2bc8ac: function() {
            return handleError(function(arg0, arg1) {
                return addHeapObject(Reflect.get(getObject(arg0), getObject(arg1)));
            }, arguments);
        },
        __wbg_get_with_ref_key_1dc361bd10053bfe: function(arg0, arg1) {
            return addHeapObject(getObject(arg0)[getObject(arg1)]);
        },
        __wbg_instanceof_ArrayBuffer_c367199e2fa2aa04: function(arg0) {
            let result;
            try {
                result = getObject(arg0) instanceof ArrayBuffer;
            } catch (_) {
                result = !1;
            }
            return result;
        },
        __wbg_instanceof_Uint8Array_9b9075935c74707c: function(arg0) {
            let result;
            try {
                result = getObject(arg0) instanceof Uint8Array;
            } catch (_) {
                result = !1;
            }
            return result;
        },
        __wbg_isArray_d314bb98fcf08331: function(arg0) {
            return Array.isArray(getObject(arg0));
        },
        __wbg_isSafeInteger_bfbc7332a9768d2a: function(arg0) {
            return Number.isSafeInteger(getObject(arg0));
        },
        __wbg_iterator_6ff6560ca1568e55: function() {
            return addHeapObject(Symbol.iterator);
        },
        __wbg_js_click_element_2fe1e774f3d232c7: function(arg0) {
            js_click_element(arg0);
        },
        __wbg_length_32ed9a279acd054c: function(arg0) {
            return getObject(arg0).length;
        },
        __wbg_length_35a7bace40f36eac: function(arg0) {
            return getObject(arg0).length;
        },
        __wbg_new_361308b2356cecd0: function() {
            return addHeapObject(new Object);
        },
        __wbg_new_3eb36ae241fe6f44: function() {
            return addHeapObject(new Array);
        },
        __wbg_new_dd2b680c8bf6ae29: function(arg0) {
            return addHeapObject(new Uint8Array(getObject(arg0)));
        },
        __wbg_next_3482f54c49e8af19: function() {
            return handleError(function(arg0) {
                return addHeapObject(getObject(arg0).next());
            }, arguments);
        },
        __wbg_next_418f80d8f5303233: function(arg0) {
            return addHeapObject(getObject(arg0).next);
        },
        __wbg_prototypesetcall_bdcdcc5842e4d77d: function(arg0, arg1, arg2) {
            Uint8Array.prototype.set.call(getArrayU8FromWasm0(arg0, arg1), getObject(arg2));
        },
        __wbg_set_3f1d0b984ed272ed: function(arg0, arg1, arg2) {
            getObject(arg0)[takeObject(arg1)] = takeObject(arg2);
        },
        __wbg_set_f43e577aea94465b: function(arg0, arg1, arg2) {
            getObject(arg0)[arg1 >>> 0] = takeObject(arg2);
        },
        __wbg_value_0546255b415e96c1: function(arg0) {
            return addHeapObject(getObject(arg0).value);
        },
        __wbindgen_cast_0000000000000001: function(arg0) {
            return addHeapObject(arg0);
        },
        __wbindgen_cast_0000000000000002: function(arg0, arg1) {
            return addHeapObject(getStringFromWasm0(arg0, arg1));
        },
        __wbindgen_cast_0000000000000003: function(arg0) {
            return addHeapObject(BigInt.asUintN(64, arg0));
        },
        __wbindgen_object_clone_ref: function(arg0) {
            return addHeapObject(getObject(arg0));
        },
        __wbindgen_object_drop_ref: function(arg0) {
            takeObject(arg0);
        }
    };
    return {
        __proto__: null,
        "./sentience_core_bg.js": import0
    };
}

function addHeapObject(obj) {
    if (heap_next === heap.length) heap.push(heap.length + 1);
    const idx = heap_next;
    heap_next = heap[idx];

    heap[idx] = obj;
    return idx;
}

function debugString(val) {
    // primitive types
    const type = typeof val;
    if (type == 'number' || type == 'boolean' || val == null) {
        return  `${val}`;
    }
    if (type == 'string') {
        return `"${val}"`;
    }
    if (type == 'symbol') {
        const description = val.description;
        if (description == null) {
            return 'Symbol';
        } else {
            return `Symbol(${description})`;
        }
    }
    if (type == 'function') {
        const name = val.name;
        if (typeof name == 'string' && name.length > 0) {
            return `Function(${name})`;
        } else {
            return 'Function';
        }
    }
    // objects
    if (Array.isArray(val)) {
        const length = val.length;
        let debug = '[';
        if (length > 0) {
            debug += debugString(val[0]);
        }
        for(let i = 1; i < length; i++) {
            debug += ', ' + debugString(val[i]);
        }
        debug += ']';
        return debug;
    }
    // Test for built-in
    const builtInMatches = /\[object ([^\]]+)\]/.exec(toString.call(val));
    let className;
    if (builtInMatches && builtInMatches.length > 1) {
        className = builtInMatches[1];
    } else {
        // Failed to match the standard '[object ClassName]'
        return toString.call(val);
    }
    if (className == 'Object') {
        // we're a user defined class or Object
        // JSON.stringify avoids problems with cycles, and is generally much
        // easier than looping through ownProperties of `val`.
        try {
            return 'Object(' + JSON.stringify(val) + ')';
        } catch (_) {
            return 'Object';
        }
    }
    // errors
    if (val instanceof Error) {
        return `${val.name}: ${val.message}\n${val.stack}`;
    }
    // TODO we could test for more things here, like `Set`s and `Map`s.
    return className;
}

function dropObject(idx) {
    if (idx < 132) return;
    heap[idx] = heap_next;
    heap_next = idx;
}

function getArrayU8FromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return getUint8ArrayMemory0().subarray(ptr / 1, ptr / 1 + len);
}

let cachedDataViewMemory0 = null;
function getDataViewMemory0() {
    return (null === cachedDataViewMemory0 || !0 === cachedDataViewMemory0.buffer.detached || void 0 === cachedDataViewMemory0.buffer.detached && cachedDataViewMemory0.buffer !== wasm.memory.buffer) && (cachedDataViewMemory0 = new DataView(wasm.memory.buffer)),
    cachedDataViewMemory0;
}

function getStringFromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return decodeText(ptr, len);
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    return null !== cachedUint8ArrayMemory0 && 0 !== cachedUint8ArrayMemory0.byteLength || (cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer)),
    cachedUint8ArrayMemory0;
}

function getObject(idx) { return heap[idx]; }

function handleError(f, args) {
    try {
        return f.apply(this, args);
    } catch (e) {
        wasm.__wbindgen_export3(addHeapObject(e));
    }
}

let heap = new Array(128).fill(undefined);
heap.push(undefined, null, true, false);

let heap_next = heap.length;

function isLikeNone(x) {
    return x === undefined || x === null;
}

function passStringToWasm0(arg, malloc, realloc) {
    if (void 0 === realloc) {
        const buf = cachedTextEncoder.encode(arg), ptr = malloc(buf.length, 1) >>> 0;
        return getUint8ArrayMemory0().subarray(ptr, ptr + buf.length).set(buf), WASM_VECTOR_LEN = buf.length,
        ptr;
    }

    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;

    const mem = getUint8ArrayMemory0();

    let offset = 0;

    for (; offset < len; offset++) {
        const code = arg.charCodeAt(offset);
        if (code > 0x7F) break;
        mem[ptr + offset] = code;
    }
    if (offset !== len) {
        if (offset !== 0) {
            arg = arg.slice(offset);
        }
        ptr = realloc(ptr, len, len = offset + arg.length * 3, 1) >>> 0;
        const view = getUint8ArrayMemory0().subarray(ptr + offset, ptr + len);
        const ret = cachedTextEncoder.encodeInto(arg, view);

        offset += ret.written;
        ptr = realloc(ptr, len, offset, 1) >>> 0;
    }

    WASM_VECTOR_LEN = offset;
    return ptr;
}

function takeObject(idx) {
    const ret = getObject(idx);
    dropObject(idx);
    return ret;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(ptr, len) {
    numBytesDecoded += len;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
        cachedTextDecoder.decode();
        numBytesDecoded = len;
    }
    return cachedTextDecoder.decode(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

const cachedTextEncoder = new TextEncoder();

"encodeInto" in cachedTextEncoder || (cachedTextEncoder.encodeInto = function(arg, view) {
    const buf = cachedTextEncoder.encode(arg);
    return view.set(buf), {
        read: arg.length,
        written: buf.length
    };
});

let wasmModule, wasm, WASM_VECTOR_LEN = 0;

function __wbg_finalize_init(instance, module) {
    return wasm = instance.exports, wasmModule = module, cachedDataViewMemory0 = null,
    cachedUint8ArrayMemory0 = null, wasm;
}

let WASM_VECTOR_LEN = 0;

/**
 * @param {any} val
 * @returns {any}
 */
export function analyze_page(val) {
    const ret = wasm.analyze_page(addHeapObject(val));
    return takeObject(ret);
}

/**
 * @param {any} val
 * @param {any} options
 * @returns {any}
 */
export function analyze_page_with_options(val, options) {
    const ret = wasm.analyze_page_with_options(addHeapObject(val), addHeapObject(options));
    return takeObject(ret);
}

/**
 * @param {any} _raw_elements
 */
export function decide_and_act(_raw_elements) {
    wasm.decide_and_act(addHeapObject(_raw_elements));
}

/**
 * Prune raw elements before sending to API
 * This is a "dumb" filter that reduces payload size without leaking proprietary IP
 * Filters out: tiny elements, invisible elements, non-interactive wrapper divs
 * Amazon: 5000-6000 elements -> ~200-400 elements (~95% reduction)
 * @param {any} val
 * @returns {any}
 */
export function prune_for_api(val) {
    const ret = wasm.prune_for_api(addHeapObject(val));
    return takeObject(ret);
}

const EXPECTED_RESPONSE_TYPES = new Set(['basic', 'cors', 'default']);

async function __wbg_load(module, imports) {
    if (typeof Response === 'function' && module instanceof Response) {
        if (typeof WebAssembly.instantiateStreaming === 'function') {
            try {
                return await WebAssembly.instantiateStreaming(module, imports);
            } catch (e) {
                const validResponse = module.ok && EXPECTED_RESPONSE_TYPES.has(module.type);

                if (validResponse && module.headers.get('Content-Type') !== 'application/wasm') {
                    console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n", e);

                } else {
                    throw e;
                }
            }
        }

        const bytes = await module.arrayBuffer();
        return await WebAssembly.instantiate(bytes, imports);
    } else {
        const instance = await WebAssembly.instantiate(module, imports);

        if (instance instanceof WebAssembly.Instance) {
            return { instance, module };
        } else {
            return instance;
        }
    }
}

function __wbg_get_imports() {
    const imports = {};
    imports.wbg = {};
    imports.wbg.__wbg_Error_52673b7de5a0ca89 = function(arg0, arg1) {
        const ret = Error(getStringFromWasm0(arg0, arg1));
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_Number_2d1dcfcf4ec51736 = function(arg0) {
        const ret = Number(getObject(arg0));
        return ret;
    };
    imports.wbg.__wbg___wbindgen_bigint_get_as_i64_6e32f5e6aff02e1d = function(arg0, arg1) {
        const v = getObject(arg1);
        const ret = typeof(v) === 'bigint' ? v : undefined;
        getDataViewMemory0().setBigInt64(arg0 + 8 * 1, isLikeNone(ret) ? BigInt(0) : ret, true);
        getDataViewMemory0().setInt32(arg0 + 4 * 0, !isLikeNone(ret), true);
    };
    imports.wbg.__wbg___wbindgen_boolean_get_dea25b33882b895b = function(arg0) {
        const v = getObject(arg0);
        const ret = typeof(v) === 'boolean' ? v : undefined;
        return isLikeNone(ret) ? 0xFFFFFF : ret ? 1 : 0;
    };
    imports.wbg.__wbg___wbindgen_debug_string_adfb662ae34724b6 = function(arg0, arg1) {
        const ret = debugString(getObject(arg1));
        const ptr1 = passStringToWasm0(ret, wasm.__wbindgen_export, wasm.__wbindgen_export2);
        const len1 = WASM_VECTOR_LEN;
        getDataViewMemory0().setInt32(arg0 + 4 * 1, len1, true);
        getDataViewMemory0().setInt32(arg0 + 4 * 0, ptr1, true);
    };
    imports.wbg.__wbg___wbindgen_in_0d3e1e8f0c669317 = function(arg0, arg1) {
        const ret = getObject(arg0) in getObject(arg1);
        return ret;
    };
    imports.wbg.__wbg___wbindgen_is_bigint_0e1a2e3f55cfae27 = function(arg0) {
        const ret = typeof(getObject(arg0)) === 'bigint';
        return ret;
    };
    imports.wbg.__wbg___wbindgen_is_function_8d400b8b1af978cd = function(arg0) {
        const ret = typeof(getObject(arg0)) === 'function';
        return ret;
    };
    imports.wbg.__wbg___wbindgen_is_object_ce774f3490692386 = function(arg0) {
        const val = getObject(arg0);
        const ret = typeof(val) === 'object' && val !== null;
        return ret;
    };
    imports.wbg.__wbg___wbindgen_is_undefined_f6b95eab589e0269 = function(arg0) {
        const ret = getObject(arg0) === undefined;
        return ret;
    };
    imports.wbg.__wbg___wbindgen_jsval_eq_b6101cc9cef1fe36 = function(arg0, arg1) {
        const ret = getObject(arg0) === getObject(arg1);
        return ret;
    };
    imports.wbg.__wbg___wbindgen_jsval_loose_eq_766057600fdd1b0d = function(arg0, arg1) {
        const ret = getObject(arg0) == getObject(arg1);
        return ret;
    };
    imports.wbg.__wbg___wbindgen_number_get_9619185a74197f95 = function(arg0, arg1) {
        const obj = getObject(arg1);
        const ret = typeof(obj) === 'number' ? obj : undefined;
        getDataViewMemory0().setFloat64(arg0 + 8 * 1, isLikeNone(ret) ? 0 : ret, true);
        getDataViewMemory0().setInt32(arg0 + 4 * 0, !isLikeNone(ret), true);
    };
    imports.wbg.__wbg___wbindgen_string_get_a2a31e16edf96e42 = function(arg0, arg1) {
        const obj = getObject(arg1);
        const ret = typeof(obj) === 'string' ? obj : undefined;
        var ptr1 = isLikeNone(ret) ? 0 : passStringToWasm0(ret, wasm.__wbindgen_export, wasm.__wbindgen_export2);
        var len1 = WASM_VECTOR_LEN;
        getDataViewMemory0().setInt32(arg0 + 4 * 1, len1, true);
        getDataViewMemory0().setInt32(arg0 + 4 * 0, ptr1, true);
    };
    imports.wbg.__wbg___wbindgen_throw_dd24417ed36fc46e = function(arg0, arg1) {
        throw new Error(getStringFromWasm0(arg0, arg1));
    };
    imports.wbg.__wbg_call_abb4ff46ce38be40 = function() { return handleError(function (arg0, arg1) {
        const ret = getObject(arg0).call(getObject(arg1));
        return addHeapObject(ret);
    }, arguments) };
    imports.wbg.__wbg_done_62ea16af4ce34b24 = function(arg0) {
        const ret = getObject(arg0).done;
        return ret;
    };
    imports.wbg.__wbg_error_7bc7d576a6aaf855 = function(arg0) {
        console.error(getObject(arg0));
    };
    imports.wbg.__wbg_get_6b7bd52aca3f9671 = function(arg0, arg1) {
        const ret = getObject(arg0)[arg1 >>> 0];
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_get_af9dab7e9603ea93 = function() { return handleError(function (arg0, arg1) {
        const ret = Reflect.get(getObject(arg0), getObject(arg1));
        return addHeapObject(ret);
    }, arguments) };
    imports.wbg.__wbg_get_with_ref_key_1dc361bd10053bfe = function(arg0, arg1) {
        const ret = getObject(arg0)[getObject(arg1)];
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_instanceof_ArrayBuffer_f3320d2419cd0355 = function(arg0) {
        let result;
        try {
            result = getObject(arg0) instanceof ArrayBuffer;
        } catch (_) {
            result = false;
        }
        const ret = result;
        return ret;
    };
    imports.wbg.__wbg_instanceof_Uint8Array_da54ccc9d3e09434 = function(arg0) {
        let result;
        try {
            result = getObject(arg0) instanceof Uint8Array;
        } catch (_) {
            result = false;
        }
        const ret = result;
        return ret;
    };
    imports.wbg.__wbg_isArray_51fd9e6422c0a395 = function(arg0) {
        const ret = Array.isArray(getObject(arg0));
        return ret;
    };
    imports.wbg.__wbg_isSafeInteger_ae7d3f054d55fa16 = function(arg0) {
        const ret = Number.isSafeInteger(getObject(arg0));
        return ret;
    };
    imports.wbg.__wbg_iterator_27b7c8b35ab3e86b = function() {
        const ret = Symbol.iterator;
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_js_click_element_2fe1e774f3d232c7 = function(arg0) {
        js_click_element(arg0);
    };
    imports.wbg.__wbg_length_22ac23eaec9d8053 = function(arg0) {
        const ret = getObject(arg0).length;
        return ret;
    };
    imports.wbg.__wbg_length_d45040a40c570362 = function(arg0) {
        const ret = getObject(arg0).length;
        return ret;
    };
    imports.wbg.__wbg_new_1ba21ce319a06297 = function() {
        const ret = new Object();
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_new_25f239778d6112b9 = function() {
        const ret = new Array();
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_new_6421f6084cc5bc5a = function(arg0) {
        const ret = new Uint8Array(getObject(arg0));
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_next_138a17bbf04e926c = function(arg0) {
        const ret = getObject(arg0).next;
        return addHeapObject(ret);
    };
    imports.wbg.__wbg_next_3cfe5c0fe2a4cc53 = function() { return handleError(function (arg0) {
        const ret = getObject(arg0).next();
        return addHeapObject(ret);
    }, arguments) };
    imports.wbg.__wbg_prototypesetcall_dfe9b766cdc1f1fd = function(arg0, arg1, arg2) {
        Uint8Array.prototype.set.call(getArrayU8FromWasm0(arg0, arg1), getObject(arg2));
    };
    imports.wbg.__wbg_set_3f1d0b984ed272ed = function(arg0, arg1, arg2) {
        getObject(arg0)[takeObject(arg1)] = takeObject(arg2);
    };
    imports.wbg.__wbg_set_7df433eea03a5c14 = function(arg0, arg1, arg2) {
        getObject(arg0)[arg1 >>> 0] = takeObject(arg2);
    };
    imports.wbg.__wbg_value_57b7b035e117f7ee = function(arg0) {
        const ret = getObject(arg0).value;
        return addHeapObject(ret);
    };
    imports.wbg.__wbindgen_cast_2241b6af4c4b2941 = function(arg0, arg1) {
        // Cast intrinsic for `Ref(String) -> Externref`.
        const ret = getStringFromWasm0(arg0, arg1);
        return addHeapObject(ret);
    };
    imports.wbg.__wbindgen_cast_4625c577ab2ec9ee = function(arg0) {
        // Cast intrinsic for `U64 -> Externref`.
        const ret = BigInt.asUintN(64, arg0);
        return addHeapObject(ret);
    };
    imports.wbg.__wbindgen_cast_d6cd19b81560fd6e = function(arg0) {
        // Cast intrinsic for `F64 -> Externref`.
        const ret = arg0;
        return addHeapObject(ret);
    };
    imports.wbg.__wbindgen_object_clone_ref = function(arg0) {
        const ret = getObject(arg0);
        return addHeapObject(ret);
    };
    imports.wbg.__wbindgen_object_drop_ref = function(arg0) {
        takeObject(arg0);
    };

    return imports;
}

function __wbg_finalize_init(instance, module) {
    wasm = instance.exports;
    __wbg_init.__wbindgen_wasm_module = module;
    cachedDataViewMemory0 = null;
    cachedUint8ArrayMemory0 = null;



    return wasm;
}

function initSync(module) {
    if (wasm !== undefined) return wasm;


    if (typeof module !== 'undefined') {
        if (Object.getPrototypeOf(module) === Object.prototype) {
            ({module} = module)
        } else {
            console.warn('using deprecated parameters for `initSync()`; pass a single object instead')
        }
    }

async function __wbg_init(module_or_path) {
    if (void 0 !== wasm) return wasm;
    void 0 !== module_or_path && Object.getPrototypeOf(module_or_path) === Object.prototype && ({module_or_path: module_or_path} = module_or_path),
    void 0 === module_or_path && (module_or_path = new URL("sentience_core_bg.wasm", import.meta.url));
    const imports = __wbg_get_imports();
    if (!(module instanceof WebAssembly.Module)) {
        module = new WebAssembly.Module(module);
    }
    const instance = new WebAssembly.Instance(module, imports);
    return __wbg_finalize_init(instance, module);
}

export { initSync, __wbg_init as default };
