import React from 'react'

const Control = () => {
    return (
        <div className='bg-secondary text-white min-h-screen flex items-center justify-center p-6 md:p-12 lg:p-20'>
            <div className='max-w-7xl w-full flex flex-col lg:flex-row gap-12 lg:gap-24 items-center'>

                {/* left - Content and Metric Lists */}
                <div className='w-full lg:w-1/2 flex flex-col space-y-10'>
                    <div>
                        <h1 className='text-5xl md:text-6xl text-white font-heading tracking-tight leading-tight mb-4'>
                            Control every dial.
                        </h1>
                        <h2 className='text-[#8b949e] font-body text-base md:text-lg leading-relaxed max-w-xl'>
                            Adjust model speed, intent threshold, and FAQ weighting per bot. Live retraining, source control on every change.
                        </h2>
                    </div>

                    <div className='flex w-full justify-between border-b border-[#21262d] pb-4 items-center'>
                        <h1 className='text-[#8b949e] font-medium'>Inference latency</h1>
                        <div className='flex items-center space-x-2 font-mono'>
                            <span>
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="w-4 h-4 text-[#8b949e]">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" />
                                </svg>
                            </span>
                            <h2 className='text-white font-semibold'>38ms</h2>
                            <h2 className='text-[#8b949e] text-xs pl-1'>p95</h2>
                        </div>
                    </div>

                    <div className='flex w-full justify-between border-b border-[#21262d] pb-4 items-center'>
                        <h1 className='text-[#8b949e] font-medium'>Intent accuracy</h1>
                        <div className='flex items-center space-x-2 font-mono'>
                            <span>
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="w-4 h-4 text-emerald-400">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" />
                                </svg>
                            </span>
                            <h2 className='text-white font-semibold'>0.94</h2>
                        </div>
                    </div>

                    <div className='flex w-full justify-between border-b border-[#21262d] pb-4 items-center'>
                        <h1 className='text-[#8b949e] font-medium'>Active bots</h1>
                        <div className='flex items-center space-x-2 font-mono'>
                            <h2 className='text-white font-semibold'>12</h2>
                            <h2 className='text-[#8b949e] text-xs pl-1'>live</h2>
                        </div>
                    </div>

                    <div className='flex w-full justify-between border-b border-[#21262d] pb-4 items-center'>
                        <h1 className='text-[#8b949e] font-medium'>Embeds served</h1>
                        <div className='flex items-center space-x-2 font-mono'>
                            <h2 className='text-white font-semibold'>184k</h2>
                            <h2 className='text-[#8b949e] text-xs pl-1'>/ mo</h2>
                        </div>
                    </div>
                </div>

                <div className='w-full lg:w-1/2 aspect-square max-w-120 border border-[#21262d] rounded-2xl bg-[#0d1117]/30 flex items-center justify-center shadow-[inset_0_0_20px_rgba(255,255,255,0.02)]'>
                    <div className="w-16 h-16 rounded-full border border-primary/30 bg-secondary flex items-center justify-center shadow-[0_0_30px_rgba(30,157,241,0.15)]">
                        <span className="text-primary">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75A2.25 2.25 0 0 0 4.5 6.75v10.5a2.25 2.25 0 0 0 2.25 2.25Zm.75-12h9v9h-9v-9Z" />
                            </svg>

                        </span>
                    </div>
                </div>

            </div>
        </div>
    )
}

export default Control;