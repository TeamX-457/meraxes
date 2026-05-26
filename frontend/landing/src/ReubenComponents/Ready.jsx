const Ready = () => {
    return (
        <div className=" font-body flex flex-col justify-between min-h-[80vh] px-6 py-12 md:px-12 lg:px-20 relative overflow-hidden">
            
            {/* Main CTA Content Area */}
            <div className=" flex flex-col items-center justify-center text-center max-w-4xl mx-auto gap-8  mb-20">
                
                {/* Heading */}
                <h1 className=" text-5xl md:text-6xl lg:text-7xl">
                    Ready to train <span className="text-primary font-normal italic">your first</span>
                    <br />
                    bot?
                </h1>

                {/* Subtitle */}
                <p className="text-primary text-base md:text-lg font-normal ">
                    Free while in beta. Self-hosted forever.
                </p>

                {/* Buttons Group */}
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4 w-full sm:w-auto">
                    <button className="w-full sm:w-auto px-8 py-3 rounded-full bg-primary  text-secondary-foreground font-medium hover:bg-secondary cursor-pointer  dark:hover:bg-white transition-colors duration-200 text-sm md:text-base">
                        Create account
                    </button>
                    <button className="w-full sm:w-auto px-8 py-3 rounded-full border border-gray-700 dark:border-white bg-transparent text-foreground font-medium hover:bg-foreground transition-colors hover:text-white dark:hover:text-black duration-200 text-sm md:text-base">
                        Log in
                    </button>
                </div>
            </div>

            {/* Footer Component */}
            <footer className="w-full border-t border-secondary/50 pt-8 mt-auto flex flex-col md:flex-row items-center justify-center text-center">
                <p className="text-foreground/60 text-xs font-mono ">
                    © 2026 Meraxes · Built for builders.
                </p>
            </footer>

        </div>
    )
}

export default Ready;